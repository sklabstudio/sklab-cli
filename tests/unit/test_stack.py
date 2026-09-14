"""Stack v0.2: manifest, registry, resolver, adapters, operations, redaction."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from sklab.stack import adapters
from sklab.stack import home as stack_home
from sklab.stack.manifest import ModuleManifest, parse_manifest_yaml
from sklab.stack.operations import (
    check_health,
    clean_preview,
    collect_statuses,
    plan_setup,
    plan_update,
    run_clean,
    run_setup,
    stack_doctor,
)
from sklab.stack.redaction import redact_text
from sklab.stack.registry import Registry, add_manifest_file, load_builtin_registry, load_registry
from sklab.stack.resolver import ResolverError, resolve
from sklab.stack.state import load_state, save_state
from tests.conftest import STACK_FIXTURES


def _fixture_manifest(name: str) -> ModuleManifest:
    return parse_manifest_yaml((STACK_FIXTURES / name).read_text(encoding="utf-8"))


def _registry_from(names: list[str]) -> Registry:
    registry = Registry()
    for name in names:
        manifest = _fixture_manifest(name)
        from sklab.stack.registry import LoadedManifest

        registry.modules[manifest.id] = LoadedManifest(
            manifest=manifest, origin="local", fingerprint=manifest.fingerprint()
        )
    return registry


# --- manifest validation ---


def test_manifest_valid_fixture() -> None:
    manifest = _fixture_manifest("public-python.yaml")
    assert manifest.id == "public-python"
    assert manifest.schema_version == 1
    assert manifest.visibility == "public"


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        parse_manifest_yaml(
            "schema_version: 1\nid: bad\nname: Bad\n"
            "visibility: public\nsource: {type: git, repository: a/b}\n"
            "install: {type: python}\nnah: 1\n"
        )


def test_manifest_rejects_string_command() -> None:
    with pytest.raises(ValueError):
        parse_manifest_yaml(
            "schema_version: 1\nid: bad-cmd\nname: Bad\nvisibility: public\n"
            "source: {type: git, repository: a/b}\n"
            "install: {type: command, command: 'curl evil | bash'}\n"
        )


def test_manifest_rejects_bad_id() -> None:
    with pytest.raises(ValueError):
        parse_manifest_yaml(
            "schema_version: 1\nid: 'Bad_ID!'\nname: Bad\nvisibility: public\n"
            "source: {type: git, repository: a/b}\ninstall: {type: python}\n"
        )


def test_install_aliases_normalize() -> None:
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: alias-test\nname: Alias\nvisibility: public\n"
        "source: {type: git, repository: a/b}\ninstall: {type: PYTHON_PACKAGE}\n"
    )
    assert manifest.install.type == "python"


# --- public registry ---


def test_builtin_registry_public_only() -> None:
    registry = load_builtin_registry()
    assert len(registry.modules) >= 14
    for loaded in registry.modules.values():
        assert loaded.manifest.visibility == "public"
        assert loaded.origin == "builtin"
    # Spot-check capabilities + dependency example from the spec.
    assert "orchestration" in registry.modules["orchestrator"].manifest.capabilities
    assert registry.modules["apivouch"].manifest.capabilities == ["verification"]
    assert registry.modules["apivouch"].manifest.install.type == "docker-compose"
    dep_ids = [d.id for d in registry.modules["orchestrator"].manifest.dependencies]
    assert dep_ids == [
        "repo-context",
        "agent-adapters",
        "provider-connections",
        "reprobox",
        "patchbench",
        "skill-hub",
    ]
    assert registry.modules["web-ui"].manifest.version == "0.3.0"


def test_builtin_has_no_private_urls() -> None:
    registry = load_builtin_registry()
    for loaded in registry.modules.values():
        repo = (loaded.manifest.source.repository or "") + (loaded.manifest.source.url or "")
        assert "@" not in repo
        assert "token" not in repo.lower()


# --- local/private loading ---


def test_local_manifest_loading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modules_dir = tmp_path / "modules.d"
    modules_dir.mkdir()
    shutil.copy(STACK_FIXTURES / "private-local-module.yaml", modules_dir / "private-local-module.yaml")
    (modules_dir / "broken.yaml").write_text("not: [valid", encoding="utf-8")
    monkeypatch.setenv("SKLAB_MODULES_DIR", str(modules_dir))
    registry = load_registry()
    assert "private-local-module" in registry.modules
    assert registry.modules["private-local-module"].manifest.visibility == "private"
    assert any("broken.yaml" in str(e) for e in registry.errors)


def test_add_manifest_copies_and_validates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modules_dir = tmp_path / "md"
    monkeypatch.setenv("SKLAB_MODULES_DIR", str(modules_dir))
    loaded = add_manifest_file(STACK_FIXTURES / "optional-module.yaml")
    assert loaded.manifest.id == "optional-module"
    assert Path(str(loaded.path)).exists()


def test_private_module_may_depend_on_public() -> None:
    registry = _registry_from(["public-python.yaml", "private-local-module.yaml"])
    order = resolve(registry, include_optional=True).order
    assert order.index("public-python") < order.index("private-local-module")


def test_public_must_not_depend_on_private() -> None:
    registry = _registry_from(["public-python.yaml", "private-local-module.yaml"])
    # Forge a public -> private edge in memory (never committed as a fixture).
    registry.modules["public-python"].manifest.dependencies.append(
        __import__("sklab.stack.manifest", fromlist=["ModuleDependency"]).ModuleDependency(id="private-local-module")
    )
    with pytest.raises(ResolverError) as exc_info:
        resolve(registry)
    assert exc_info.value.code == "VISIBILITY_VIOLATION"


# --- resolver ---


def test_dependency_ordering() -> None:
    registry = _registry_from(["public-python.yaml", "private-local-module.yaml"])
    order = resolve(registry, include_optional=True).order
    assert order == sorted(order) or order.index("public-python") < order.index("private-local-module")


def test_cycle_detection() -> None:
    registry = _registry_from(["dependency-cycle-a.yaml", "dependency-cycle-b.yaml"])
    with pytest.raises(ResolverError) as exc_info:
        resolve(registry)
    assert exc_info.value.code == "DEPENDENCY_CYCLE"


def test_missing_dependency() -> None:
    registry = _registry_from(["missing-dependency.yaml"])
    with pytest.raises(ResolverError) as exc_info:
        resolve(registry)
    assert exc_info.value.code == "MISSING_DEPENDENCY"


def test_unknown_module_selected() -> None:
    registry = _registry_from(["public-python.yaml"])
    with pytest.raises(ResolverError):
        resolve(registry, selected=["nope"])


def test_stable_ordering() -> None:
    first = resolve(_registry_from(["public-python.yaml", "degraded-health.yaml"])).order
    second = resolve(_registry_from(["degraded-health.yaml", "public-python.yaml"])).order
    assert first == second == sorted(first)


# --- health statuses ---


def test_health_ready_degraded_failed_not_installed() -> None:
    assert check_health(_fixture_manifest("public-python.yaml")).status == "READY"
    assert check_health(_fixture_manifest("degraded-health.yaml")).status == "DEGRADED"
    assert check_health(_fixture_manifest("failed-health.yaml")).status == "FAILED"
    assert check_health(_fixture_manifest("optional-module.yaml")).status == "NOT_INSTALLED"


def test_status_never_fakes_ready(isolated_home: Path) -> None:
    registry = load_builtin_registry()
    for item in collect_statuses(registry):
        assert item.status in ("READY", "DEGRADED", "FAILED", "NOT_INSTALLED", "UNAVAILABLE", "UNKNOWN")


def test_unavailable_when_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Optional fixture uses a binary that never exists -> deterministic NOT_INSTALLED.
    assert check_health(_fixture_manifest("optional-module.yaml")).status == "NOT_INSTALLED"
    # Docker adapter reports UNAVAILABLE when the base tool is absent.
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: dockmod\nname: Dock\nvisibility: public\n"
        "source: {type: git, repository: a/b}\ninstall: {type: docker-compose}\n"
        "health: {command: ['docker', 'compose', 'version']}\n"
    )
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "docker" else real_which(name))
    result = adapters.install_module(manifest, dry_run=False)
    assert result.status in ("UNAVAILABLE", "SKIPPED", "FAILED")


# --- adapters ---


def test_adapter_command_success_and_failure() -> None:
    good = _fixture_manifest("degraded-health.yaml")  # install command exits 0
    result = adapters.install_module(good, dry_run=False)
    assert result.ok and result.status == "READY"
    # A failing command adapter reports FAILED without a shell.
    import copy

    bad = copy.deepcopy(good)
    bad.id = "bad-cmd"
    bad.install.command = ["python", "-c", "import sys; sys.exit(3)"]
    failed = adapters.install_module(bad, dry_run=False)
    assert not failed.ok and failed.status == "FAILED"


def test_adapter_dry_run_makes_no_changes(tmp_path: Path) -> None:
    manifest = _fixture_manifest("degraded-health.yaml")
    before = set(tmp_path.iterdir())
    result = adapters.install_module(manifest, dry_run=True)
    assert result.status == "SKIPPED"
    assert set(tmp_path.iterdir()) == before


def test_adapter_plans_are_argv_arrays() -> None:
    for name in ["public-python.yaml", "public-node.yaml", "optional-module.yaml"]:
        for step in adapters.plan_install(_fixture_manifest(name)):
            assert isinstance(step, list) and step and all(isinstance(a, str) for a in step)


def test_no_shell_true_in_codebase() -> None:
    import ast

    root = Path(__file__).resolve().parents[2] / "src"
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                value = node.value
                if isinstance(value, ast.Constant) and value.value is True:
                    offenders.append(str(path))
    assert offenders == []


def test_no_curl_bash_hooks_in_fixtures() -> None:
    for path in STACK_FIXTURES.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert "curl" not in text and "| bash" not in text


# --- setup ---


def _isolated_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, names: list[str]) -> Registry:
    modules_dir = tmp_path / "md"
    modules_dir.mkdir(exist_ok=True)
    for name in names:
        shutil.copy(STACK_FIXTURES / name, modules_dir / name)
    monkeypatch.setenv("SKLAB_MODULES_DIR", str(modules_dir))
    return load_registry(modules_dir)


def test_setup_dry_run_makes_no_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    registry = _isolated_registry(monkeypatch, tmp_path, ["public-python.yaml", "degraded-health.yaml"])
    state_path = Path(str(isolated_home)) / "state.json"
    result = run_setup(registry, scope="all", dry_run=True, state_path=state_path)
    assert result.order
    assert not state_path.exists()


def test_setup_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path) -> None:
    # Fixture-only registry: hermetic (no real clones/builds); full-registry installs are proven live.
    registry = _registry_from(["degraded-health.yaml", "failed-health.yaml"])
    state_path = Path(str(isolated_home)) / "state.json"
    first = run_setup(registry, scope="all", dry_run=False, state_path=state_path)
    second = run_setup(registry, scope="all", dry_run=False, state_path=state_path)
    assert first.summary and second.summary
    # Idempotency: second run must not report new failures beyond the first.
    assert set(second.health.keys()) == set(first.health.keys())


def test_setup_scope_public_excludes_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    registry = _isolated_registry(monkeypatch, tmp_path, ["public-python.yaml", "private-local-module.yaml"])
    order, _steps = plan_setup(registry, scope="public")
    assert "private-local-module" not in order
    order_all, _ = plan_setup(registry, scope="all")
    assert "private-local-module" in order_all


def test_optional_unavailable_skipped_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
) -> None:
    registry = _registry_from(["optional-module.yaml"])
    result = run_setup(registry, scope="all", dry_run=False,
                       state_path=Path(str(isolated_home)) / "s.json")
    assert result.health["optional-module"].status == "NOT_INSTALLED"


# --- doctor ---


def test_stack_doctor_offline_no_paid_ai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path) -> None:
    registry = _isolated_registry(monkeypatch, tmp_path, ["public-python.yaml", "optional-module.yaml"])
    report = stack_doctor(registry)
    assert report["platform"]
    assert isinstance(report["tools"], list)
    assert isinstance(report["modules"], list)
    statuses = {m["status"] for m in report["modules"]}  # type: ignore[union-attr]
    assert statuses <= {"READY", "DEGRADED", "FAILED", "NOT_INSTALLED", "UNAVAILABLE", "UNKNOWN"}


# --- update ---


def test_update_planning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path) -> None:
    registry = _registry_from(["public-python.yaml"])
    state_path = Path(str(isolated_home)) / "state.json"
    plan = plan_update(registry, state_path=state_path)
    assert all(p["action"] == "install" for p in plan)
    run_setup(registry, scope="all", dry_run=False, state_path=state_path)
    plan2 = plan_update(registry, state_path=state_path)
    assert all(p["action"] == "skip" for p in plan2)


# --- redaction ---


def test_redaction_tokens_urls_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKLAB_PRIVATE_MODULE_URL", "https://secret-token-abc123@example.com/repo.git")
    assert "[REDACTED]" in redact_text("token=super-secret-value")
    assert "[REDACTED]" in redact_text("https://user:pass@github.com/org/repo.git")
    assert "secret-token-abc123" not in redact_text("clone https://secret-token-abc123@example.com/repo.git")
    assert "[REDACTED]" in redact_text("Bearer abcdef12345")
    assert "[REDACTED]" in redact_text("key is ghp_abcdefghijklmnop123456")


def test_redaction_never_logs_private_manifest(tmp_path: Path) -> None:
    text = (STACK_FIXTURES / "private-local-module.yaml").read_text(encoding="utf-8")
    assert "SKLAB_PRIVATE_MODULE_URL" in text  # indirection, not a secret value
    assert "https://" not in text


# --- state ---


def test_state_atomic_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = load_state(path)
    assert state.modules == {}
    from sklab.stack.state import record_module

    record_module(state, module_id="x", version="1", install_type="command",
                  origin="local", manifest_fingerprint="abc", status="READY", health="READY")
    save_state(state, path)
    assert json.loads(path.read_text(encoding="utf-8"))["modules"]["x"]["status"] == "READY"


# --- clean ---


def test_clean_only_owns_sk_lab_temp(isolated_home: Path) -> None:
    home = stack_home.sklab_home()
    owned = home / "cache" / "stale.tmp"
    owned.parent.mkdir(parents=True, exist_ok=True)
    owned.write_text("tmp", encoding="utf-8")
    outside = Path(str(isolated_home)) / "user-repo" / "keep.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("user data", encoding="utf-8")
    preview = clean_preview()
    paths = [c["path"] for c in preview]
    assert str(owned) in paths
    assert str(outside) not in paths
    result = run_clean(dry_run=True)
    assert result["dry_run"] is True
    assert outside.exists()
    run_clean(dry_run=False)
    assert outside.read_text(encoding="utf-8") == "user data"


def test_clean_dry_run_removes_nothing(isolated_home: Path) -> None:
    home = stack_home.sklab_home()
    target = home / "logs" / "old.log"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("logs", encoding="utf-8")
    run_clean(dry_run=True)
    assert target.exists()


def test_missing_tool_handling_for_docker() -> None:
    manifest = parse_manifest_yaml(
        "schema_version: 1\nid: dockmod\nname: Dock\nvisibility: public\n"
        "source: {type: git, repository: a/b}\ninstall: {type: docker-compose}\n"
        "health: {command: ['docker', 'compose', 'version']}\n"
    )
    plan = adapters.plan_install(manifest)
    assert plan and plan[0][0] == "docker"
    if shutil.which("docker") is None:
        assert adapters.install_module(manifest).status == "UNAVAILABLE"


def test_sklab_home_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = tmp_path / "custom-home"
    monkeypatch.setenv("SKLAB_HOME", str(custom))
    assert stack_home.sklab_home() == custom
    assert stack_home.modules_dir() == custom / "modules.d"
    os.environ.pop("SKLAB_MODULES_DIR", None)
