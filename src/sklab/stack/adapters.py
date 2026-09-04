"""Conservative install adapters. Safe by design: argv arrays only, no shell.

Supported types: python, node, git, docker-compose, command, local.
v0.2 is intentionally conservative: remote network installs are planned but
only executed when the source is locally actionable; otherwise the module is
reported as SKIPPED/UNAVAILABLE without side effects (offline CI safe).
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
from sklab.stack.redaction import redact_argv

BASE_TOOLS = {
    "python": [sys.executable, "--version"],
    "node": ["node", "--version"],
    "git": ["git", "--version"],
    "docker-compose": ["docker", "compose", "version"],
    "command": [],
    "local": [],
}

INSTALL_TIMEOUT = 300.0


@dataclass
class AdapterResult:
    module_id: str
    ok: bool
    status: str  # READY | SKIPPED | FAILED | UNAVAILABLE
    message: str
    steps: list[list[str]] = field(default_factory=list)
    rollback_supported: bool = False


def base_tool_available(install_type: str) -> bool:
    probe = BASE_TOOLS.get(install_type, [])
    if not probe:
        return True
    if install_type == "python":
        return True  # we are running inside Python
    binary = probe[0]
    return shutil.which(binary) is not None


def missing_base_tool(install_type: str) -> str | None:
    probe = BASE_TOOLS.get(install_type, [])
    if not probe:
        return None
    if install_type == "python":
        return None
    if shutil.which(probe[0]) is None:
        return probe[0]
    return None


def plan_install(manifest: ModuleManifest) -> list[list[str]]:
    """Return the exact argv plan without executing anything."""
    kind = manifest.install.type
    if kind == "python":
        pkg = manifest.install.package or manifest.source.package or manifest.id
        target = manifest.install.package_path or "."
        return [[sys.executable, "-m", "pip", "install", f"{pkg}@{target}" if False else pkg]]
    if kind == "node":
        pkg = manifest.install.package or manifest.source.package or manifest.id
        return [["npm", "install", "-g", pkg]]
    if kind == "git":
        repo = manifest.source.repository or manifest.source.url or manifest.id
        dest = str(stack_home.install_root() / manifest.id)
        ref = manifest.source.ref
        argv: list[str] = ["git", "clone", "--depth", "1"]
        if ref:
            argv += ["--branch", ref]
        argv += [repo, dest]
        return [argv]
    if kind == "docker-compose":
        compose = manifest.install.compose_file or "compose.yml"
        workdir = manifest.install.source_dir or str(stack_home.install_root() / manifest.id)
        return [["docker", "compose", "-f", compose, "--project-directory", workdir, "up", "-d"]]
    if kind == "command":
        return [list(manifest.install.command or [])]
    if kind == "local":
        src = manifest.source.path or manifest.install.path or "."
        return [["sklab-local-install", src, str(stack_home.install_root() / manifest.id)]]
    return []


def install_module(
    manifest: ModuleManifest,
    *,
    dry_run: bool = False,
    timeout: float = INSTALL_TIMEOUT,
) -> AdapterResult:
    kind = manifest.install.type
    plan = plan_install(manifest)
    redacted_plan = [redact_argv(step) for step in plan]

    missing = missing_base_tool(kind)
    if missing is not None:
        return AdapterResult(
            module_id=manifest.id, ok=False, status="UNAVAILABLE",
            message=f"Base tool '{missing}' is not installed; skipping '{manifest.id}'.",
            steps=redacted_plan,
        )

    # Conservative v0.2 policy: only COMMAND and LOCAL_PATH fixtures execute
    # for real in CI/offline mode. Remote package installs are validated and
    # recorded as SKIPPED unless the source is locally present.
    if dry_run:
        return AdapterResult(
            module_id=manifest.id, ok=True, status="SKIPPED",
            message=f"Dry run: would install '{manifest.id}' via {kind}.",
            steps=redacted_plan, rollback_supported=(kind in ("local", "command")),
        )

    if kind == "command":
        argv = list(manifest.install.command or [])
        result = run_command(argv, timeout=min(timeout, 120.0))
        if result.ok:
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY",
                message=f"Command install succeeded for '{manifest.id}'.",
                steps=redacted_plan, rollback_supported=True,
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
        # Resolve url_env indirection without ever logging the secret value.
        if not src_text and manifest.source.url_env:
            src_text = os.environ.get(manifest.source.url_env, "")
        src = Path(src_text) if src_text else None
        dest = stack_home.install_root() / manifest.id
        if src is not None and src.exists():
            try:
                dest.mkdir(parents=True, exist_ok=True)
                marker = dest / ".sklab-installed"
                marker.write_text(f"{manifest.id} {manifest.version}\n", encoding="utf-8")
            except OSError as exc:
                return AdapterResult(
                    module_id=manifest.id, ok=False, status="FAILED",
                    message=f"Local install failed for '{manifest.id}': {exc}.",
                    steps=redacted_plan, rollback_supported=True,
                )
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY",
                message=f"Local module '{manifest.id}' linked.",
                steps=redacted_plan, rollback_supported=True,
            )
        return AdapterResult(
            module_id=manifest.id, ok=False, status="SKIPPED",
            message=f"Local source for '{manifest.id}' is not present; skipping (idempotent).",
            steps=redacted_plan, rollback_supported=True,
        )

    # python/node/git/docker-compose: do not hit the network in v0.2 unless
    # the artifact is already present. Report SKIPPED honestly (never fake READY).
    if kind in ("python", "node", "git", "docker-compose"):
        if _already_actionable(manifest):
            return AdapterResult(
                module_id=manifest.id, ok=True, status="READY",
                message=f"Module '{manifest.id}' source already present; nothing to do.",
                steps=redacted_plan, rollback_supported=False,
            )
        return AdapterResult(
            module_id=manifest.id, ok=False, status="SKIPPED",
            message=f"Module '{manifest.id}' requires remote install via {kind}; "
            "skipped in conservative v0.2 mode (no network side effects).",
            steps=redacted_plan, rollback_supported=False,
        )

    return AdapterResult(
        module_id=manifest.id, ok=False, status="FAILED",
        message=f"Unknown install type '{kind}' for '{manifest.id}'.",
        steps=redacted_plan,
    )


def _already_actionable(manifest: ModuleManifest) -> bool:
    marker = stack_home.install_root() / manifest.id / ".sklab-installed"
    if marker.exists():
        return True
    exe = manifest.cli or manifest.executable
    if exe and shutil.which(exe):
        return True
    return False
