"""Real install adapters. Safe by design: argv arrays only, no shell.

Supported types: python, node, git, docker-compose, command, local.

v0.3 turns the v0.2 conservative planner into a REAL idempotent installer:
non-dry-run setup performs network/system installs after explicit user
confirmation. Dry-run performs zero mutation (pure inspection).

Every adapter exposes plan/install/update/verify/uninstall semantics through
install_module/update_module/verify_module/uninstall_module with structured
AdapterResult objects.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sklab.core.subprocess import run_command
from sklab.stack import home as stack_home
from sklab.stack.manifest import ModuleManifest
from sklab.stack.redaction import redact_argv, redact_text

BASE_TOOLS = {
    "python": [sys.executable, "--version"],
    "node": ["node", "--version"],
    "git": ["git", "--version"],
    "docker-compose": ["docker", "compose", "version"],
    "command": [],
    "local": [],
}

INSTALL_TIMEOUT = 600.0
GIT_TIMEOUT = 300.0
NETWORK_TIMEOUT = 240.0


@dataclass
class AdapterResult:
    module_id: str
    ok: bool
    status: str  # READY | SKIPPED | FAILED | UNAVAILABLE | AUTH_REQUIRED | NO_CHANGE
    message: str
    steps: list[list[str]] = field(default_factory=list)
    rollback_supported: bool = False
    changed: bool = False
    auth_required: bool = False


def base_tool_available(install_type: str) -> bool:
    return missing_base_tool(install_type) is None


def missing_base_tool(install_type: str) -> str | None:
    probe = BASE_TOOLS.get(install_type, [])
    if not probe:
        return None
    if install_type == "python":
        return None
    if shutil.which(probe[0]) is None:
        return probe[0]
    return None


# --- safe path helpers --------------------------------------------------------


def safe_module_dir(base: Path, module_id: str) -> Path:
    """Join a module id without traversal. Id regex already constrains, double-check."""
    if "/" in module_id or "\\" in module_id or ".." in module_id:
        raise ValueError(f"Unsafe module id: {module_id!r}.")
    target = base / module_id
    try:
        target.resolve().relative_to(base.resolve())
    except (ValueError, OSError) as exc:
        raise ValueError(f"Module path escapes install root: {module_id!r}.") from exc
    return target


def resolve_local_source(path_text: str) -> Path | None:
    if not path_text:
        return None
    candidate = Path(path_text).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved


def repo_url_for(manifest: ModuleManifest) -> str | None:
    if manifest.source.url:
        return manifest.source.url
    if manifest.source.repository:
        repo = manifest.source.repository.strip()
        if repo.startswith(("http://", "https://", "git@", "ssh://", "file://")):
            return repo
        if "/" in repo and " " not in repo:
            return f"https://github.com/{repo}.git"
        return None
    if manifest.source.url_env:
        value = os.environ.get(manifest.source.url_env, "")
        return value or None
    return None


def auth_required_for(manifest: ModuleManifest) -> bool:
    """Private manifest whose source needs credentials that are absent."""
    if manifest.visibility != "private":
        return False
    if manifest.source.url_env and not os.environ.get(manifest.source.url_env):
        return True
    return False


def marker_path(module_id: str) -> Path:
    return safe_module_dir(stack_home.install_root(), module_id) / ".sklab-installed"


def write_marker(module_id: str, version: str, extra: str = "") -> None:
    marker = marker_path(module_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    content = f"{module_id} {version} v0.3\n{extra}\n" if extra else f"{module_id} {version} v0.3\n"
    marker.write_text(content, encoding="utf-8")


# --- plan (pure, no side effects) ----------------------------------------------


def plan_install(manifest: ModuleManifest) -> list[list[str]]:
    """Return the exact argv plan without executing anything. No network, no mutation."""
    kind = manifest.install.type
    if kind == "python":
        dest = safe_module_dir(stack_home.repos_dir(), manifest.id)
        pkg = manifest.install.package or manifest.source.package or manifest.id
        return [
            ["git", "clone", "--depth", "1", f"https://github.com/{manifest.source.repository}.git", str(dest)]
            if manifest.source.repository else [sys.executable, "-m", "pip", "install", pkg],
            [sys.executable, "-m", "pip", "install", str(manifest.install.package_path or ".")],
        ]
    if kind == "node":
        dest = safe_module_dir(stack_home.repos_dir(), manifest.id)
        return [
            ["git", "clone", "--depth", "1", f"https://github.com/{manifest.source.repository}.git", str(dest)]
            if manifest.source.repository else ["npm", "install", "-g", manifest.install.package or manifest.id],
            ["npm", "ci"],
            ["npm", "run", "build"],
        ]
    if kind == "git":
        url = repo_url_for(manifest) or manifest.id
        dest_str = str(safe_module_dir(stack_home.repos_dir(), manifest.id))
        argv: list[str] = ["git", "clone", "--depth", "1"]
        if manifest.source.ref:
            argv += ["--branch", manifest.source.ref]
        argv += [url, dest_str]
        return [argv]
    if kind == "docker-compose":
        compose = manifest.install.compose_file or "compose.yml"
        workdir = manifest.install.source_dir or str(safe_module_dir(stack_home.repos_dir(), manifest.id))
        return [["docker", "compose", "-f", compose, "--project-directory", workdir, "up", "-d"]]
    if kind == "command":
        return [list(manifest.install.command or [])]
    if kind == "local":
        src = manifest.source.path or manifest.install.path or "."
        return [["sklab-local-install", src, str(safe_module_dir(stack_home.install_root(), manifest.id))]]
    return []


# --- git primitives -------------------------------------------------------------


def _git_checkout(manifest: ModuleManifest, *, timeout: float) -> AdapterResult:
    url = repo_url_for(manifest)
    redacted_url = redact_text(url or manifest.id)
    if auth_required_for(manifest):
        return AdapterResult(
            module_id=manifest.id, ok=False, status="AUTH_REQUIRED",
            message=f"Private module '{manifest.id}' needs ${manifest.source.url_env} or "
            "authenticated git (gh auth login). Public install continues.",
            steps=[], auth_required=True,
        )
    if not url:
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"No git source for '{manifest.id}'.", steps=[],
        )
    dest = safe_module_dir(stack_home.repos_dir(), manifest.id)
    if dest.exists() and (dest / ".git").exists():
        # Idempotent fetch: never destroy user changes; fast-forward only.
        fetch = run_command(["git", "-C", str(dest), "fetch", "origin"], timeout=timeout)
        if not fetch.ok:
            return AdapterResult(
                module_id=manifest.id, ok=False, status="FAILED",
                message=f"git fetch failed for '{manifest.id}': {redact_text(fetch.stderr[:300])}.",
                steps=[[ "git", "-C", str(dest), "fetch", "origin"]],
            )
        if manifest.source.ref:
            checkout = run_command(["git", "-C", str(dest), "checkout", manifest.source.ref], timeout=60.0)
            if not checkout.ok:
                return AdapterResult(
                    module_id=manifest.id, ok=False, status="FAILED",
                    message=f"git checkout {manifest.source.ref} failed for '{manifest.id}'.",
                    steps=[],
                )
            return AdapterResult(
                module_id=manifest.id, ok=True, status="NO_CHANGE",
                message=f"'{manifest.id}' already cloned; ref {manifest.source.ref} verified.",
                steps=[], changed=False,
            )
        pull = run_command(["git", "-C", str(dest), "pull", "--ff-only"], timeout=timeout)
        if pull.ok:
            changed = "Already up to date." not in (pull.stdout + pull.stderr)
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY" if changed else "NO_CHANGE",
                message=f"'{manifest.id}' updated." if changed else f"'{manifest.id}' already up to date.",
                steps=[], changed=changed,
            )
        # Local changes block ff-only: preserve, report honestly, do not force.
        return AdapterResult(
            module_id=manifest.id, ok=True, status="NO_CHANGE",
            message=f"'{manifest.id}' has local changes; fetch succeeded, no overwrite (resume with git pull).",
            steps=[], changed=False,
        )
    if dest.exists() and not (dest / ".git").exists():
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"Destination {dest} exists but is not a git repo; refusing to overwrite.",
            steps=[],
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    argv: list[str] = ["git", "clone", "--depth", "1"]
    if manifest.source.ref:
        argv += ["--branch", manifest.source.ref]
    argv += [url, str(dest)]
    clone = run_command(argv, timeout=timeout)
    if not clone.ok:
        combined = (clone.stderr + clone.stdout)
        if "Authentication failed" in combined or "could not read Username" in combined or "403" in combined:
            return AdapterResult(
                module_id=manifest.id, ok=False, status="AUTH_REQUIRED",
                message=f"Authenticated access required for '{manifest.id}' ({redacted_url}). "
                "Run 'gh auth login'; public install continues.",
                steps=[redact_argv(argv)], auth_required=True,
            )
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"git clone failed for '{manifest.id}' ({redacted_url}): {redact_text(clone.stderr[:300])}.",
            steps=[redact_argv(argv)],
        )
    return AdapterResult(
        module_id=manifest.id, ok=True, status="READY",
        message=f"Cloned '{manifest.id}'.", steps=[redact_argv(argv)], changed=True,
    )


# --- per-type install -----------------------------------------------------------


def _install_python(manifest: ModuleManifest, *, timeout: float) -> AdapterResult:
    checkout: AdapterResult | None = None
    repo: Path | None = None
    if manifest.source.repository or manifest.source.type == "git":
        checkout = _git_checkout(manifest, timeout=min(timeout, GIT_TIMEOUT))
        if checkout.status == "AUTH_REQUIRED":
            return checkout
        if not checkout.ok:
            return checkout
        repo = safe_module_dir(stack_home.repos_dir(), manifest.id)
    # Prefer pipx for CLI modules, else isolated venv, else user pip.
    # Standard layouts put the project at the root or one level down (backend/, server/, api/).
    target_dir = _find_python_project(repo) if repo is not None else None
    if target_dir is None:
        pkg = manifest.install.package or manifest.source.package
        if pkg:
            return _pip_install_package(manifest, pkg, timeout=timeout)
        if checkout is not None and checkout.ok:
            # Content repo (no Python project): the verified clone IS the install.
            write_marker(manifest.id, manifest.version, extra=f"git {repo}")
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY",
                message=f"Cloned '{manifest.id}' (content repo, nothing to build).",
                steps=checkout.steps, changed=checkout.changed,
            )
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"No Python package source for '{manifest.id}'.", steps=[],
        )
    pipx = shutil.which("pipx")
    if pipx:
        # NOTE: bare `pipx install` exits 0 without touching an existing venv
        # ("already seems to be installed"), which once left stale module code
        # in place while setup reported success. --force recreates the venv
        # from the current source on every run (idempotent, just slower).
        pipx_argv = [pipx, "install", "--force", str(target_dir)]
        result = run_command(pipx_argv, timeout=timeout)
        if result.ok:
            write_marker(manifest.id, manifest.version, extra=f"pipx {target_dir}")
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY",
                message=f"pipx installed '{manifest.id}'.", steps=[pipx_argv],
                changed=True,
            )
        # Fall through to venv on pipx failure (honest message preserved).
        pipx_error = redact_text((result.stderr or result.stdout)[:300])
    else:
        pipx_error = "pipx not installed"
    venv_result = _pip_install_into_venv(manifest, target_dir, timeout=timeout)
    if not venv_result.ok and not venv_result.steps:
        # Preserve the pipx context when venv creation itself failed.
        venv_result.message = (
            f"venv creation failed for '{manifest.id}' "
            f"({pipx_error}; {venv_result.message})"
        )
    return venv_result


def _looks_like_python_project(path: Path) -> bool:
    return ((path / "pyproject.toml").exists() or (path / "setup.py").exists() or (path / "setup.cfg").exists())


def _find_python_project(repo: Path) -> Path | None:
    """Root first, then one standard subdir level (backend/, server/, api/). Pure inspection."""
    if _looks_like_python_project(repo):
        return repo
    for child in ("backend", "server", "api"):
        candidate = repo / child
        try:
            if candidate.is_dir() and _looks_like_python_project(candidate):
                return candidate
        except OSError:
            continue
    return None


def _find_node_app(repo: Path) -> Path | None:
    """Root first, then one standard subdir level (frontend/, client/, app/, web/). Pure inspection."""
    if (repo / "package.json").is_file():
        return repo
    for child in ("frontend", "client", "app", "web"):
        candidate = repo / child / "package.json"
        try:
            if candidate.is_file():
                return candidate.parent
        except OSError:
            continue
    return None


def _has_npm_script(app_dir: Path, script: str) -> bool:
    import json as _json

    try:
        data = _json.loads((app_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    scripts = data.get("scripts")
    return isinstance(scripts, dict) and script in scripts


def _pip_install_package(manifest: ModuleManifest, package: str, *, timeout: float) -> AdapterResult:
    result = run_command([sys.executable, "-m", "pip", "install", package], timeout=timeout)
    if result.ok:
        write_marker(manifest.id, manifest.version, extra=f"pip {package}")
        return AdapterResult(
            module_id=manifest.id, ok=True, status="READY",
            message=f"pip installed '{package}'.",
            steps=[[sys.executable, "-m", "pip", "install", redact_text(package)]], changed=True,
        )
    return AdapterResult(
        module_id=manifest.id, ok=False, status="FAILED",
        message=f"pip install failed for '{manifest.id}': {redact_text((result.stderr or result.stdout)[:300])}.",
        steps=[[sys.executable, "-m", "pip", "install", redact_text(package)]],
    )


def _install_node(manifest: ModuleManifest, *, timeout: float) -> AdapterResult:
    from sklab.stack.preflight import check_node

    node_info = check_node()
    if node_info["verdict"] in ("NOT_INSTALLED", "FAILED"):
        return AdapterResult(
            module_id=manifest.id, ok=False, status="UNAVAILABLE",
            message=f"Node unavailable for '{manifest.id}': {node_info['detail']}", steps=[],
        )
    if manifest.source.repository or manifest.source.type == "git":
        checkout = _git_checkout(manifest, timeout=min(timeout, GIT_TIMEOUT))
        if checkout.status == "AUTH_REQUIRED":
            return checkout
        if not checkout.ok:
            return checkout
        repo_dir = safe_module_dir(stack_home.repos_dir(), manifest.id)
    else:
        pkg = manifest.install.package or manifest.source.package
        if pkg:
            npm_result = run_command(["npm", "install", "-g", pkg], timeout=timeout)
            if npm_result.ok:
                write_marker(manifest.id, manifest.version, extra=f"npm -g {pkg}")
                return AdapterResult(
                    module_id=manifest.id, ok=True, status="READY",
                    message=f"npm installed '{pkg}'.", steps=[["npm", "install", "-g", pkg]], changed=True,
                )
            return AdapterResult(
                module_id=manifest.id, ok=False, status="FAILED",
                message=f"npm install failed for '{manifest.id}': "
                f"{redact_text((npm_result.stderr or npm_result.stdout)[:300])}.",
                steps=[["npm", "install", "-g", pkg]],
            )
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"No Node package source for '{manifest.id}'.", steps=[],
        )
    # Real frontend install: npm ci (or install) + build when defined. Sequential, no parallelism.
    app_dir = _find_node_app(repo_dir)
    if app_dir is None:
        write_marker(manifest.id, manifest.version, extra=f"git {repo_dir}")
        return checkout
    lock = app_dir / "package-lock.json"
    install_argv = ["npm", "ci"] if lock.exists() else ["npm", "install"]
    installed = run_command(install_argv, cwd=app_dir, timeout=timeout)
    if not installed.ok:
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"npm install failed for '{manifest.id}': "
            f"{redact_text((installed.stderr or installed.stdout)[:300])}.",
            steps=[install_argv],
        )
    steps = [install_argv]
    backend_dir = _find_python_project(repo_dir)
    if backend_dir is not None and backend_dir != app_dir:
        backend_result = _pip_install_into_venv(manifest, backend_dir, timeout=timeout)
        steps.extend(backend_result.steps)
        if not backend_result.ok:
            return AdapterResult(
                module_id=manifest.id, ok=False, status="FAILED",
                message=f"Backend install failed for '{manifest.id}': {backend_result.message} "
                "Fix it and re-run setup to resume.",
                steps=steps,
            )
    if _has_npm_script(app_dir, "build"):
        build_argv = ["npm", "run", "build"]
        built = run_command(build_argv, cwd=app_dir, timeout=timeout)
        steps.append(build_argv)
        if not built.ok:
            # Build failure still leaves dependencies installed; report honestly.
            write_marker(manifest.id, manifest.version, extra=f"npm-install-only {app_dir}")
            return AdapterResult(
                module_id=manifest.id, ok=False, status="FAILED",
                message=f"npm build failed for '{manifest.id}': "
                f"{redact_text((built.stderr or built.stdout)[:300])}. "
                "Dependencies installed; fix the build and re-run setup to resume.",
                steps=steps,
            )
    write_marker(manifest.id, manifest.version, extra=f"npm {app_dir}")
    warning = ""
    if node_info["verdict"] == "DEGRADED":
        warning = f" Note: {node_info['detail']}"
    return AdapterResult(
        module_id=manifest.id, ok=True, status="READY",
        message=f"Node dependencies + build done for '{manifest.id}'.{warning}",
        steps=steps, changed=True,
    )


def _pip_install_into_venv(manifest: ModuleManifest, target_dir: Path, *, timeout: float) -> AdapterResult:
    """Install a project dir into an isolated per-module venv. No sudo, no system pip."""
    venv_dir = stack_home.venvs_dir() / manifest.id
    if not (venv_dir / "bin" / "activate").exists() and not (venv_dir / "Scripts" / "activate.bat").exists():
        created = run_command([sys.executable, "-m", "venv", str(venv_dir)], timeout=120.0)
        if not created.ok:
            return AdapterResult(
                module_id=manifest.id, ok=False, status="FAILED",
                message=f"venv creation failed for '{manifest.id}': {redact_text(created.stderr[:200])}.",
                steps=[],
            )
    pip_bin = str(venv_dir / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip"))
    # NOTE: plain `pip install <dir>` is a same-version no-op ("already
    # satisfied") that would leave stale code behind while reporting success.
    # --force-reinstall guarantees the venv matches the current source.
    install_argv = [pip_bin, "install", "--force-reinstall", str(target_dir)]
    installed = run_command(install_argv, timeout=timeout)
    if installed.ok:
        write_marker(manifest.id, manifest.version, extra=f"venv {venv_dir}")
        return AdapterResult(
            module_id=manifest.id, ok=True, status="READY",
            message=f"Installed '{manifest.id}' into isolated venv.",
            steps=[install_argv], changed=True,
        )
    return AdapterResult(
        module_id=manifest.id, ok=False, status="FAILED",
        message=f"pip install failed for '{manifest.id}': {redact_text((installed.stderr or installed.stdout)[:300])}.",
        steps=[install_argv],
    )


def _install_docker_compose(manifest: ModuleManifest, *, timeout: float) -> AdapterResult:
    from sklab.stack.preflight import check_docker

    docker = check_docker()
    if docker["status"] != "READY":
        status = "UNAVAILABLE" if docker["status"] in ("NOT_INSTALLED", "DAEMON_UNAVAILABLE") else "FAILED"
        return AdapterResult(
            module_id=manifest.id, ok=False, status=status,
            message=f"Docker not ready for '{manifest.id}': {docker['detail']}", steps=[],
        )
    if manifest.install.source_dir:
        workdir = Path(manifest.install.source_dir)
    else:
        workdir = safe_module_dir(stack_home.repos_dir(), manifest.id)
        if manifest.source.repository and not (workdir / ".git").exists():
            checkout = _git_checkout(manifest, timeout=min(timeout, GIT_TIMEOUT))
            if not checkout.ok and checkout.status != "NO_CHANGE":
                return checkout
    compose_file = manifest.install.compose_file or "compose.yml"
    compose_path = workdir / compose_file
    if not compose_path.exists():
        # Fall back to any compose file the repo defines; never invent one.
        for candidate in ("compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"):
            if (workdir / candidate).exists():
                compose_file = candidate
                compose_path = workdir / candidate
                break
    if not compose_path.exists():
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"No compose file ({compose_file}) in {workdir}; refusing to invent one.", steps=[],
        )
    argv = ["docker", "compose", "-f", str(compose_path), "--project-directory", str(workdir), "up", "-d"]
    started = run_command(argv, timeout=timeout)
    if started.ok:
        write_marker(manifest.id, manifest.version, extra=f"compose {compose_path}")
        return AdapterResult(
            module_id=manifest.id, ok=True, status="READY",
            message=f"Compose services up for '{manifest.id}'.", steps=[argv], changed=True,
        )
    return AdapterResult(
        module_id=manifest.id, ok=False, status="FAILED",
        message=f"docker compose failed for '{manifest.id}': {redact_text((started.stderr or started.stdout)[:300])}.",
        steps=[argv],
    )


# --- main entry points ----------------------------------------------------------


def install_module(
    manifest: ModuleManifest,
    *,
    dry_run: bool = False,
    timeout: float = INSTALL_TIMEOUT,
) -> AdapterResult:
    kind = manifest.install.type
    plan = plan_install(manifest)
    redacted_plan = [redact_argv(step) for step in plan]

    if dry_run:
        # Absolute purity: no network, no filesystem mutation, no auth prompts.
        return AdapterResult(
            module_id=manifest.id, ok=True, status="SKIPPED",
            message=f"Dry run: would install '{manifest.id}' via {kind}.",
            steps=redacted_plan, rollback_supported=(kind in ("local", "command")),
        )

    missing = missing_base_tool(kind)
    if missing is not None:
        return AdapterResult(
            module_id=manifest.id, ok=False, status="UNAVAILABLE",
            message=f"Base tool '{missing}' is not installed; skipping '{manifest.id}'.",
            steps=redacted_plan,
        )

    if auth_required_for(manifest):
        return AdapterResult(
            module_id=manifest.id, ok=False, status="AUTH_REQUIRED",
            message=f"Private module '{manifest.id}' needs ${manifest.source.url_env}; "
            "run 'gh auth login' or export the variable. Public install continues.",
            steps=redacted_plan, auth_required=True,
        )

    if kind == "command":
        argv = list(manifest.install.command or [])
        result = run_command(argv, timeout=min(timeout, 120.0))
        if result.ok:
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY",
                message=f"Command install succeeded for '{manifest.id}'.",
                steps=redacted_plan, rollback_supported=True, changed=True,
            )
        if result.not_found:
            return AdapterResult(
                module_id=manifest.id, ok=False, status="UNAVAILABLE",
                message=f"Install command not found for '{manifest.id}': {redact_argv(argv)[0]}.",
                steps=redacted_plan,
            )
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"Install command failed for '{manifest.id}' (exit {result.returncode}).",
            steps=redacted_plan, rollback_supported=True,
        )

    if kind == "local":
        src_text = manifest.source.path or manifest.install.path or ""
        if not src_text and manifest.source.url_env:
            src_text = os.environ.get(manifest.source.url_env, "")
            if manifest.visibility == "private" and not src_text:
                return AdapterResult(
                    module_id=manifest.id, ok=False, status="AUTH_REQUIRED",
                    message=f"Private module '{manifest.id}' needs ${manifest.source.url_env}.",
                    steps=redacted_plan, auth_required=True,
                )
        src = resolve_local_source(src_text)
        dest = safe_module_dir(stack_home.install_root(), manifest.id)
        if src is not None and src.exists():
            try:
                dest.mkdir(parents=True, exist_ok=True)
                write_marker(manifest.id, manifest.version, extra=f"local {src}")
            except OSError as exc:
                return AdapterResult(
                    module_id=manifest.id, ok=False, status="FAILED",
                    message=f"Local install failed for '{manifest.id}': {exc}.",
                    steps=redacted_plan, rollback_supported=True,
                )
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY",
                message=f"Local module '{manifest.id}' linked.",
                steps=redacted_plan, rollback_supported=True, changed=True,
            )
        if manifest.visibility == "private":
            return AdapterResult(
                module_id=manifest.id, ok=False, status="AUTH_REQUIRED",
                message=f"Private source for '{manifest.id}' is not accessible; "
                "authenticate (gh auth login) or set the source path. Public install continues.",
                steps=redacted_plan, auth_required=True,
            )
        return AdapterResult(
            module_id=manifest.id, ok=False, status="SKIPPED",
            message=f"Local source for '{manifest.id}' is not present; skipping (idempotent).",
            steps=redacted_plan, rollback_supported=True,
        )

    if kind == "git":
        git_result = _git_checkout(manifest, timeout=min(timeout, GIT_TIMEOUT))
        if git_result.ok and git_result.status in ("READY", "NO_CHANGE"):
            repo_path = safe_module_dir(stack_home.repos_dir(), manifest.id)
            write_marker(manifest.id, manifest.version, extra=f"git {repo_path}")
        git_result.steps = git_result.steps or redacted_plan
        return git_result

    if kind == "python":
        return _install_python(manifest, timeout=min(timeout, NETWORK_TIMEOUT))

    if kind == "node":
        return _install_node(manifest, timeout=min(timeout, NETWORK_TIMEOUT))

    if kind == "docker-compose":
        return _install_docker_compose(manifest, timeout=min(timeout, NETWORK_TIMEOUT))

    return AdapterResult(
        module_id=manifest.id, ok=False, status="FAILED",
        message=f"Unknown install type '{kind}' for '{manifest.id}'.",
        steps=redacted_plan,
    )


def update_module(manifest: ModuleManifest, *, timeout: float = INSTALL_TIMEOUT) -> AdapterResult:
    """Safe update: fetch/pull ff-only for git; reinstall for python/node; no destructive resets."""
    kind = manifest.install.type
    if kind == "git":
        result = _git_checkout(manifest, timeout=min(timeout, GIT_TIMEOUT))
        if result.ok:
            write_marker(manifest.id, manifest.version, extra="updated")
        return result
    if kind in ("python", "node"):
        # Re-run install (idempotent: skips when READY is handled by caller; here force re-verify).
        return install_module(manifest, timeout=timeout)
    if kind == "docker-compose":
        return install_module(manifest, timeout=timeout)
    return install_module(manifest, timeout=timeout)


def verify_module(manifest: ModuleManifest) -> AdapterResult:
    from sklab.stack.operations import check_health

    health = check_health(manifest)
    ok = health.status == "READY"
    return AdapterResult(
        module_id=manifest.id, ok=ok,
        status="READY" if ok else health.status,
        message=f"Verify {manifest.id}: {health.status} - {health.detail}",
        steps=[],
    )


def uninstall_module(manifest: ModuleManifest) -> AdapterResult:
    """Remove only SKLab-owned artifacts: marker, venv, checkout. Never user repos elsewhere."""
    removed: list[str] = []
    try:
        marker = marker_path(manifest.id)
        if marker.exists():
            marker.unlink(missing_ok=True)
            removed.append(str(marker))
        venv = stack_home.venvs_dir() / manifest.id
        if venv.exists():
            shutil.rmtree(venv, ignore_errors=True)
            removed.append(str(venv))
        checkout = safe_module_dir(stack_home.repos_dir(), manifest.id)
        if checkout.exists() and (checkout / ".git").exists():
            shutil.rmtree(checkout, ignore_errors=True)
            removed.append(str(checkout))
    except OSError as exc:
        return AdapterResult(
            module_id=manifest.id, ok=False, status="FAILED",
            message=f"Uninstall failed for '{manifest.id}': {exc}.", steps=[],
        )
    return AdapterResult(
        module_id=manifest.id, ok=True, status="READY",
        message=f"Uninstalled '{manifest.id}' ({len(removed)} owned artifact(s) removed).",
        steps=[], rollback_supported=False, changed=bool(removed),
    )


def _already_actionable(manifest: ModuleManifest) -> bool:
    if marker_path(manifest.id).exists():
        return True
    exe = manifest.cli or manifest.executable
    if exe and shutil.which(exe):
        return True
    return False
