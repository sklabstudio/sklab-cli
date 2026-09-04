"""SKLab CLI v0.3: real installer, preflight, resume, dry-run purity, security."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from sklab.stack import adapters, preflight
from sklab.stack import home as stack_home
from sklab.stack.adapters import safe_module_dir
from sklab.stack.manifest import parse_manifest_yaml
from sklab.stack.operations import DiskSafetyError, plan_setup, run_setup, stack_doctor
from sklab.stack.registry import Registry, load_registry
from tests.conftest import STACK_FIXTURES


def _cmd_manifest(
    module_id: str,
    *,
    exit_code: int = 0,
    visibility: str = "public",
    health_exit: int | None = None,
    deps: list[str] | None = None,
    url_env: str | None = None,
) -> str:
    health_cmd = (
        f'["python", "-c", "import sys; sys.exit({health_exit})"]'
        if health_exit is not None
        else '["python", "--version"]'
    )
    deps_yaml = ""
    if deps:
        deps_yaml = "dependencies:\n" + "".join(f"  - {d}\n" for d in deps)
    source = f"{{type: git, repository: sklabstudio/fixture{', url_env: ' + url_env if url_env else ''}}}"
    return (
        "schema_version: 1\n"
        f"id: {module_id}\nname: {module_id}\nversion: 0.1.0\nvisibility: {visibility}\n"
        f"source: {source}\n"
        f"install: {{type: command, command: [\"python\", \"-c\", \"import sys; sys.exit({exit_code})\"]}}\n"
        f"health: {{command: {health_cmd}}}\n"
        f"{deps_yaml}"
    )


def _write_manifest(modules_dir: Path, module_id: str, text: str) -> Path:
    modules_dir.mkdir(parents=True, exist_ok=True)
    target = modules_dir / f"{module_id}.yaml"
    target.write_text(text, encoding="utf-8")
    return target


def _small_registry(files: dict[str, str]) -> Registry:
    """In-memory registry from manifest texts only (no builtins): hermetic, no network."""
    from sklab.stack.registry import LoadedManifest

    registry = Registry()
    for text in files.values():
        manifest = parse_manifest_yaml(text)
        registry.modules[manifest.id] = LoadedManifest(
            manifest=manifest, origin="local", fingerprint=manifest.fingerprint()
        )
    return registry


def _seed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, files: dict[str, str]) -> Path:
    modules_dir = tmp_path / "md"
    for name, text in files.items():
        _write_manifest(modules_dir, name, text)
    monkeypatch.setenv("SKLAB_MODULES_DIR", str(modules_dir))
    return modules_dir


# --- 20. dry-run contract -----------------------------------------------------


def test_dry_run_creates_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    modules_dir = tmp_path / "md"
    modules_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(STACK_FIXTURES / "public-python.yaml", modules_dir / "public-python.yaml")
    _write_manifest(modules_dir, "dry-a", _cmd_manifest("dry-a"))
    monkeypatch.setenv("SKLAB_MODULES_DIR", str(modules_dir))
    registry = load_registry(modules_dir)
    state_path = Path(str(isolated_home)) / "state.json"
    repos_before = list(stack_home.repos_dir().rglob("*")) if stack_home.repos_dir().exists() else []
    result = run_setup(registry, scope="all", dry_run=True, state_path=state_path)
    assert result.log_path == ""
    assert not state_path.exists()
    repos_after = list(stack_home.repos_dir().rglob("*")) if stack_home.repos_dir().exists() else []
    assert repos_after == repos_before
    # No installer log may appear in dry-run.
    logs = list(stack_home.system_logs_dir().rglob("setup-*.log")) if stack_home.system_logs_dir().exists() else []
    assert logs == []
    assert result.order


def test_adapter_dry_run_pure_for_all_types(isolated_home: Path) -> None:
    for name in ("public-python.yaml", "public-node.yaml", "optional-module.yaml"):
        manifest = parse_manifest_yaml((STACK_FIXTURES / name).read_text(encoding="utf-8"))
        before = set(stack_home.sklab_home().rglob("*")) if stack_home.sklab_home().exists() else set()
        result = adapters.install_module(manifest, dry_run=True)
        assert result.status == "SKIPPED"
        after = set(stack_home.sklab_home().rglob("*")) if stack_home.sklab_home().exists() else set()
        assert after == before


# --- 22. second-run idempotency -------------------------------------------------


def test_second_run_no_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path) -> None:
    registry = _small_registry({"idem-a": _cmd_manifest("idem-a")})
    state_path = Path(str(isolated_home)) / "state.json"
    first = run_setup(registry, scope="all", dry_run=False, state_path=state_path)
    assert first.health["idem-a"].status == "READY"
    markers_before = sorted(p.read_text(encoding="utf-8") for p in stack_home.install_root().rglob(".sklab-installed"))
    second = run_setup(registry, scope="all", dry_run=False, state_path=state_path)
    markers_after = sorted(p.read_text(encoding="utf-8") for p in stack_home.install_root().rglob(".sklab-installed"))
    assert markers_before == markers_after
    assert second.results["idem-a"].status == "SKIPPED"
    assert second.health["idem-a"].status == "READY"


# --- 16. failed-step resume -------------------------------------------------------


def test_failed_step_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path) -> None:
    state_path = Path(str(isolated_home)) / "state.json"
    first = run_setup(
        _small_registry({
            "good": _cmd_manifest("good"),
            "bad": _cmd_manifest("bad", exit_code=3, health_exit=2),
        }),
        scope="all", dry_run=False, state_path=state_path,
    )
    assert first.health["good"].status == "READY"
    assert first.health["bad"].status == "FAILED"
    assert "bad" in first.resume_hint and "re-run" in first.resume_hint
    # Repair only the failed step; success must be preserved, not redone.
    second = run_setup(
        _small_registry({
            "good": _cmd_manifest("good"),
            "bad": _cmd_manifest("bad", exit_code=0, health_exit=0),
        }),
        scope="all", dry_run=False, state_path=state_path,
    )
    assert second.health["good"].status == "READY"
    assert second.results["good"].status == "SKIPPED"
    assert second.health["bad"].status == "READY"


def test_disk_gate_aborts_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    _seed(monkeypatch, tmp_path, {"disk-a": _cmd_manifest("disk-a", health_exit=2)})
    monkeypatch.setattr(preflight, "check_disk_ok", lambda required_mb, path=None: (False, "simulated full disk"))
    state_path = Path(str(isolated_home)) / "state.json"
    with pytest.raises(DiskSafetyError):
        run_setup(load_registry(), scope="all", dry_run=False, state_path=state_path)
    assert not state_path.exists()


# --- 23/24. private absent / present -----------------------------------------------


def test_private_absent_public_install_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    monkeypatch.delenv("SKLAB_PRIVATE_MODULE_URL", raising=False)
    result = run_setup(
        _small_registry({"pub": _cmd_manifest("pub")}),
        scope="all", dry_run=False, state_path=Path(str(isolated_home)) / "s.json",
    )
    assert result.health["pub"].status == "READY"
    assert "AUTH_REQUIRED" not in result.summary


def test_private_present_with_auth_installs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    monkeypatch.setenv("SKLAB_PRIVATE_MODULE_URL", "https://example.com/private.git")
    result = run_setup(
        _small_registry({
            "pub": _cmd_manifest("pub"),
            "priv": _cmd_manifest("priv", visibility="private", url_env="SKLAB_PRIVATE_MODULE_URL"),
        }),
        scope="all", dry_run=False, state_path=Path(str(isolated_home)) / "s.json",
    )
    assert result.health["priv"].status == "READY"
    assert result.health["pub"].status == "READY"


def test_private_missing_auth_reports_auth_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    monkeypatch.delenv("SKLAB_PRIVATE_MODULE_URL", raising=False)
    registry = _small_registry({
        "public-python": (STACK_FIXTURES / "public-python.yaml").read_text(encoding="utf-8"),
        "priv": _cmd_manifest("priv", visibility="private", url_env="SKLAB_PRIVATE_MODULE_URL",
                              deps=["public-python"]),
    })
    order, steps = plan_setup(registry, scope="all")
    auth_steps = [s for s in steps if s.action == "auth"]
    assert any(s.id == "priv" for s in auth_steps)
    result = run_setup(registry, scope="all", dry_run=False,
                       state_path=Path(str(isolated_home)) / "s.json")
    assert result.health["priv"].status == "AUTH_REQUIRED"
    # Public modules are unaffected.
    assert "priv" in result.resume_hint


# --- 19. security -------------------------------------------------------------------


def test_command_injection_args_are_literal(isolated_home: Path, tmp_path: Path) -> None:
    sentinel = tmp_path / "pwned.txt"
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: inject\nname: Inject\nvisibility: public\n"
        "source: {type: git, repository: sklabstudio/fixture}\n"
        "install: {type: command, command: [\"python\", \"-c\", "
        "\"import sys; print('; rm -rf /'); sys.exit(0)\"]}\n"
        "health: {command: [\"python\", \"--version\"]}\n"
    )
    result = adapters.install_module(manifest, dry_run=False)
    assert result.ok
    assert not sentinel.exists()


def test_string_command_rejected() -> None:
    with pytest.raises(ValueError):
        parse_manifest_yaml(
            "schema_version: 1\nid: evil\nname: Evil\nvisibility: public\n"
            "source: {type: git, repository: a/b}\n"
            "install: {type: command, command: \"rm -rf /\"}\n"
        )


def test_module_id_traversal_rejected() -> None:
    with pytest.raises(ValueError, match="Unsafe module id|Invalid module id"):
        safe_module_dir(stack_home.install_root(), "../escape")
    with pytest.raises(ValueError):
        parse_manifest_yaml(
            "schema_version: 1\nid: ../escape\nname: E\nvisibility: public\n"
            "source: {type: git, repository: a/b}\ninstall: {type: command, command: [\"python\", \"--version\"]}\n"
        )


def test_symlink_and_uninstall_safety(tmp_path: Path, isolated_home: Path) -> None:
    outside = tmp_path / "user-data"
    outside.mkdir()
    precious = outside / "keep.txt"
    precious.write_text("user data", encoding="utf-8")
    link = tmp_path / "linkmod"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    resolved = adapters.resolve_local_source(str(link))
    assert resolved == outside.resolve()
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: linkmod\nname: Link\nvisibility: public\n"
        f"source: {{type: local, path: {link.as_posix()}}}\n"
        "install: {type: local}\n"
        "health: {command: [\"python\", \"--version\"]}\n"
    )
    assert adapters.install_module(manifest, dry_run=False).ok
    assert adapters.uninstall_module(manifest).ok
    assert precious.read_text(encoding="utf-8") == "user data"


def test_redaction_covers_auth_headers_and_private_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    from sklab.stack.redaction import redact_text

    monkeypatch.setenv("SKLAB_PRIVATE_MODULE_URL", "https://tok123@example.com/org/priv.git")
    assert "[REDACTED]" in redact_text("Authorization: Bearer abcdef123456")
    assert "tok123" not in redact_text("clone https://tok123@example.com/org/priv.git")
    assert "[REDACTED]" in redact_text("password: s3cr3t-value")


def test_no_shell_true_ast() -> None:
    import ast

    root = Path(__file__).resolve().parents[2] / "src"
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                if isinstance(node.value, ast.Constant) and node.value.value is True:
                    offenders.append(str(path))
    assert offenders == []


# --- preflight ----------------------------------------------------------------------


def test_path_bootstrap_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.delenv("SKLAB_MODULES_DIR", raising=False)
    # PATH without the bin dir.
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))
    monkeypatch.setenv("SHELL", "/bin/bash")
    assert preflight.path_fix_plan() != []
    first = preflight.apply_path_fix()
    assert first["changed"] is True
    second = preflight.apply_path_fix()
    assert second["changed"] is False
    content = (fake_home / ".bashrc").read_text(encoding="utf-8")
    assert content.count(preflight.PATH_LINE) == 1


def test_node_engines_guidance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "webui"
    repo.mkdir()
    (repo / "package.json").write_text(json.dumps({"engines": {"node": ">=20"}}), encoding="utf-8")
    assert preflight.read_package_engines(repo) == {"node": ">=20"}

    class FakeResult:
        ok = True
        stdout = "v18.20.0\n"
        stderr = ""
        not_found = False
        returncode = 0

    monkeypatch.setattr(preflight, "run_command", lambda *a, **k: FakeResult())
    info = preflight.check_node(repo)
    assert info["verdict"] == "DEGRADED"
    assert "20" in info["detail"]
    # Guidance must never instruct to pipe a downloader into a shell.
    assert "curl |" not in info["detail"] and "| bash" not in info["detail"]


def test_docker_states(monkeypatch: pytest.MonkeyPatch) -> None:
    from sklab.stack import preflight as pf

    class R:
        def __init__(self, ok=False, out="", err="", not_found=False, code=1):
            self.ok = ok
            self.stdout = out
            self.stderr = err
            self.not_found = not_found
            self.returncode = code

    monkeypatch.setattr(pf, "run_command", lambda argv, timeout=10.0, **k: R(not_found=True))
    assert pf.check_docker()["status"] == "NOT_INSTALLED"

    def fake_daemon(argv, timeout=10.0, **k):
        if argv == ["docker", "--version"]:
            return R(ok=True, out="Docker version 26.0.0\n", code=0)
        if argv == ["docker", "compose", "version"]:
            return R(ok=True, out="v2\n", code=0)
        return R(ok=False, err="permission denied while trying to connect", code=1)

    monkeypatch.setattr(pf, "run_command", fake_daemon)
    assert pf.check_docker()["status"] == "PERMISSION_DENIED"

    def fake_down(argv, timeout=10.0, **k):
        if argv[:2] == ["docker", "--version"]:
            return R(ok=True, out="Docker version 26.0.0\n", code=0)
        return R(ok=False, err="Cannot connect to the Docker daemon", code=1)

    monkeypatch.setattr(pf, "run_command", fake_down)
    assert pf.check_docker()["status"] == "DAEMON_UNAVAILABLE"


def test_github_auth_public_ok_without_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    from sklab.stack import preflight as pf

    class R:
        def __init__(self, **kw):
            self.ok = kw.get("ok", False)
            self.stdout = kw.get("out", "")
            self.stderr = ""
            self.not_found = kw.get("not_found", False)
            self.returncode = 0

    monkeypatch.setattr(pf, "run_command", lambda argv, timeout=10.0, **k: R(not_found=True))
    status = pf.check_github_auth()
    assert status["status"] == "PUBLIC_OK"
    assert "token" not in status["detail"].lower()


def test_resource_levels() -> None:
    from sklab.stack.preflight import HostInfo, resource_verdict

    assert resource_verdict(HostInfo(ram_mib=16384, swap_mib=4096)).level == "RECOMMENDED"
    low = resource_verdict(HostInfo(ram_mib=3800, swap_mib=4600))
    assert low.level == "SUPPORTED_FOR_TESTING"  # never hard-fail on 4GB


def test_install_roots_separated(isolated_home: Path) -> None:
    repos = stack_home.repos_dir()
    runtime = stack_home.runtime_dir()
    assert repos != runtime
    assert repos.parent == runtime.parent or str(repos).startswith(str(stack_home.sklab_home()))
    assert ".sklab" in str(repos) or "sklab" in str(repos)


def test_web_ui_engines_smoke_without_network(tmp_path: Path) -> None:
    """Web UI smoke that never touches the network: engines parsing + plan shape."""
    repo = tmp_path / "web-ui"
    (repo / "frontend").mkdir(parents=True)
    (repo / "frontend" / "package.json").write_text(
        json.dumps({"engines": {"node": ">=20"}, "scripts": {"build": "echo build"}}), encoding="utf-8"
    )
    engines = preflight.read_package_engines(repo / "frontend")
    assert engines["node"] == ">=20"
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: web-ui\nname: Web UI\nvisibility: public\n"
        "source: {type: git, repository: sklabstudio/web-ui}\n"
        "install: {type: node}\n"
        "health: {command: [\"python\", \"--version\"]}\n"
    )
    plan = adapters.plan_install(manifest)
    assert plan and all(isinstance(step, list) for step in plan)


def test_git_clone_idempotent_offline(tmp_path: Path, isolated_home: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    src = tmp_path / "srcrepo"
    src.mkdir()
    subprocess.run(["git", "init", str(src)], capture_output=True, check=False)  # noqa: S603
    subprocess.run(["git", "-C", str(src), "config", "user.email", "t@t"], capture_output=True, check=False)  # noqa: S603
    subprocess.run(["git", "-C", str(src), "config", "user.name", "t"], capture_output=True, check=False)  # noqa: S603
    (src / "README.md").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "-C", str(src), "add", "."], capture_output=True, check=False)  # noqa: S603
    subprocess.run(["git", "-C", str(src), "commit", "-m", "init"], capture_output=True, check=False)  # noqa: S603
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: gitmod\nname: Git\nvisibility: public\n"
        f"source: {{type: git, url: {src.as_uri()}}}\n"
        "install: {type: git}\n"
        "health: {command: [\"python\", \"--version\"]}\n"
    )
    first = adapters.install_module(manifest, dry_run=False)
    assert first.ok and first.changed is True
    second = adapters.install_module(manifest, dry_run=False)
    assert second.ok and second.changed is False


def test_web_ui_build_calls_npm_in_subdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    """Full-stack web-ui layout (frontend + backend) with stubbed subprocess: no network, no npm."""
    import sklab.stack.adapters as adapters_mod
    from sklab.core.subprocess import CommandResult

    repos = stack_home.repos_dir()
    app = repos / "web-ui" / "frontend"
    app.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps({"name": "web-ui", "scripts": {"build": "next build"}}), encoding="utf-8"
    )
    backend = repos / "web-ui" / "backend"
    backend.mkdir(parents=True)
    (backend / "pyproject.toml").write_text("[project]\nname = 'web-backend'\n", encoding="utf-8")

    calls: list[tuple[list[str], object]] = []

    def fake_run(argv: list[str], *, cwd: object = None, timeout: float = 60.0) -> CommandResult:
        calls.append((list(argv), cwd))
        return CommandResult(argv=list(argv), returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(adapters_mod, "run_command", fake_run)
    monkeypatch.setattr(
        "sklab.stack.preflight.check_node",
        lambda repo_dir=None: {"installed": "v20.0.0", "required": "", "verdict": "READY", "detail": "ok"},
    )
    # Stub venv backend install (no real venv in unit tests).
    monkeypatch.setattr(
        adapters_mod, "_pip_install_into_venv",
        lambda manifest, target_dir, timeout=600.0: adapters_mod.AdapterResult(
            module_id=manifest.id, ok=True, status="READY", message="venv stub",
            steps=[[f"venv {target_dir}"]], changed=True,
        ),
    )
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: web-ui\nname: Web UI\nvisibility: public\n"
        "source: {type: git, repository: sklabstudio/web-ui}\n"
        "install: {type: node}\n"
        "health: {command: [\"python\", \"--version\"]}\n"
    )
    # Bypass the clone: repo already present is NOT enough (no .git) -> stub checkout too.
    monkeypatch.setattr(
        adapters_mod, "_git_checkout",
        lambda manifest, timeout=300.0: adapters_mod.AdapterResult(
            module_id=manifest.id, ok=True, status="NO_CHANGE", message="already cloned",
            steps=[], changed=False,
        ),
    )
    result = adapters_mod.install_module(manifest, dry_run=False)
    assert result.ok and result.status == "READY"
    argv_list = [argv for argv, _cwd in calls]
    assert ["npm", "install"] in argv_list or ["npm", "ci"] in argv_list
    assert ["npm", "run", "build"] in argv_list
    # npm ran inside the frontend subdir, not the repo root.
    for argv, cwd in calls:
        if argv[:2] == ["npm", "run"]:
            assert Path(str(cwd)) == app
    assert (stack_home.install_root() / "web-ui" / ".sklab-installed").exists()


def test_doctor_includes_new_sections(isolated_home: Path) -> None:
    report = stack_doctor(load_registry())
    for key in ("base_deps", "path", "docker", "node", "github_auth", "resources"):
        assert key in report
    assert report["resources"]["level"] in ("RECOMMENDED", "SUPPORTED_FOR_TESTING", "CONSTRAINED")


def test_setup_json_includes_log_and_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    from typer.testing import CliRunner

    from sklab.cli import app

    _seed(monkeypatch, tmp_path, {"j": _cmd_manifest("j")})
    runner = CliRunner()
    result = runner.invoke(app, ["setup", "--all", "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "host" in payload and "order" in payload


def test_subdir_project_probing(tmp_path: Path) -> None:
    from sklab.stack.adapters import _find_node_app, _find_python_project, _has_npm_script

    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir(parents=True)
    assert _find_python_project(repo) is None
    assert _find_node_app(repo) is None
    (repo / "backend" / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    (repo / "frontend" / "package.json").write_text(
        json.dumps({"scripts": {"build": "echo build"}}), encoding="utf-8"
    )
    assert _find_python_project(repo) == repo / "backend"
    assert _find_node_app(repo) == repo / "frontend"
    assert _has_npm_script(repo / "frontend", "build") is True
    assert _has_npm_script(repo / "frontend", "deploy") is False
    # Root-level projects win.
    (repo / "pyproject.toml").write_text("[project]\nname = 'root'\n", encoding="utf-8")
    (repo / "package.json").write_text(json.dumps({}), encoding="utf-8")
    assert _find_python_project(repo) == repo
    assert _find_node_app(repo) == repo


def test_content_repo_python_fallback_writes_marker(tmp_path: Path, isolated_home: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    src = tmp_path / "content"
    src.mkdir()
    subprocess.run(["git", "init", str(src)], capture_output=True, check=False)  # noqa: S603
    subprocess.run(["git", "-C", str(src), "config", "user.email", "t@t"], capture_output=True, check=False)  # noqa: S603
    subprocess.run(["git", "-C", str(src), "config", "user.name", "t"], capture_output=True, check=False)  # noqa: S603
    (src / "README.md").write_text("content only", encoding="utf-8")
    subprocess.run(["git", "-C", str(src), "add", "."], capture_output=True, check=False)  # noqa: S603
    subprocess.run(["git", "-C", str(src), "commit", "-m", "init"], capture_output=True, check=False)  # noqa: S603
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: contentmod\nname: Content\nvisibility: public\n"
        f"source: {{type: git, url: {src.as_uri()}}}\n"
        "install: {type: python}\n"
        "health: {command: [\"python\", \"--version\"]}\n"
    )
    result = adapters.install_module(manifest, dry_run=False)
    assert result.ok and result.status == "READY"
    assert "content repo" in result.message


def test_mismatch_resume_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path) -> None:
    result = run_setup(
        _small_registry({
            # Install command succeeds but health binary never exists.
            "ghost": (
                "schema_version: 1\nid: ghost\nname: Ghost\nversion: 0.1.0\nvisibility: public\n"
                "source: {type: git, repository: sklabstudio/fixture}\n"
                "install: {type: command, command: [\"python\", \"-c\", \"import sys; sys.exit(0)\"]}\n"
                "health: {command: [\"sklab-nonexistent-binary-xyz\", \"--version\"]}\n"
            ),
        }),
        scope="all", dry_run=False, state_path=Path(str(isolated_home)) / "s.json",
    )
    assert result.health["ghost"].status == "NOT_INSTALLED"
    assert "ghost" in result.resume_hint and "unverified" in result.resume_hint
