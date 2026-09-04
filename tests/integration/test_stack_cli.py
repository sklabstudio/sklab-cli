"""CLI integration for stack commands: setup/status/doctor/modules/update/clean (offline)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from sklab.cli import app
from tests.conftest import STACK_FIXTURES


def _invoke(runner: CliRunner, *args: str):  # type: ignore[no-untyped-def]
    return runner.invoke(app, list(args))


def _seed_modules(tmp_path: Path, monkeypatch, names: list[str]) -> Path:  # type: ignore[no-untyped-def]
    modules_dir = tmp_path / "md"
    modules_dir.mkdir(exist_ok=True)
    for name in names:
        shutil.copy(STACK_FIXTURES / name, modules_dir / name)
    monkeypatch.setenv("SKLAB_MODULES_DIR", str(modules_dir))
    return modules_dir


def test_modules_lists_public(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "modules")
    assert result.exit_code == 0, result.output
    assert "orchestrator" in result.output


def test_modules_json_valid(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "modules", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    ids = {m["id"] for m in payload["modules"]}
    assert "orchestrator" in ids and "web-ui" in ids


def test_modules_add_manifest_private(
    runner: CliRunner, isolated_home: Path, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    _seed_modules(tmp_path, monkeypatch, [])
    result = _invoke(runner, "modules", "add-manifest", str(STACK_FIXTURES / "private-local-module.yaml"))
    assert result.exit_code == 0, result.output
    result = _invoke(runner, "modules", "--json")
    payload = json.loads(result.output)
    ids = {m["id"] for m in payload["modules"]}
    assert "private-local-module" in ids


def test_status_table_and_json(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "status")
    assert result.exit_code == 0, result.output
    assert "SKLab status" in result.output
    result = _invoke(runner, "status", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "modules" in payload
    statuses = {m["status"] for m in payload["modules"]}
    assert statuses <= {"READY", "DEGRADED", "FAILED", "NOT_INSTALLED", "UNAVAILABLE", "UNKNOWN"}


def test_setup_dry_run_all_json(
    runner: CliRunner, isolated_home: Path, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    _seed_modules(tmp_path, monkeypatch, ["public-python.yaml", "optional-module.yaml"])
    result = _invoke(runner, "setup", "--all", "--dry-run", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert "order" in payload and "plan" in payload


def test_setup_public_dry_run_table(
    runner: CliRunner, isolated_home: Path, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    _seed_modules(tmp_path, monkeypatch, ["public-python.yaml"])
    result = _invoke(runner, "setup", "--public", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "setup plan" in result.output.lower()


def test_setup_rejects_all_and_public(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "setup", "--all", "--public", "--dry-run")
    assert result.exit_code != 0


def test_doctor_stack_json(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "doctor", "--stack", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "tools" in payload and "modules" in payload
    assert "dependency_consistency" in payload


def test_doctor_stack_table(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "doctor", "--stack")
    assert result.exit_code == 0, result.output
    assert "SKLab Doctor" in result.output


def test_doctor_repo_still_works(runner: CliRunner, isolated_home: Path) -> None:
    from tests.conftest import FIXTURES

    result = _invoke(runner, "doctor", "--path", str(FIXTURES / "projects" / "python-only"))
    assert result.exit_code == 0, result.output
    assert "SKLab Doctor" in result.output


def test_module_install_dry_run_and_doctor(
    runner: CliRunner, isolated_home: Path, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    _seed_modules(tmp_path, monkeypatch, ["degraded-health.yaml"])
    result = _invoke(runner, "module", "install", "degraded-health", "--dry-run", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["dry_run"] is True
    result = _invoke(runner, "module", "doctor", "degraded-health", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "DEGRADED"


def test_module_install_unknown(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "module", "install", "nope")
    assert result.exit_code != 0


def test_update_dry_run_json(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "update", "--dry-run", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["dry_run"] is True


def test_clean_dry_run_json(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "clean", "--dry-run", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["dry_run"] is True


def test_json_modes_emit_valid_json_only(runner: CliRunner, isolated_home: Path) -> None:
    for args in [
        ("status", "--json"),
        ("modules", "--json"),
        ("setup", "--public", "--dry-run", "--json"),
        ("doctor", "--stack", "--json"),
        ("update", "--dry-run", "--json"),
        ("clean", "--dry-run", "--json"),
    ]:
        result = _invoke(runner, *args)
        assert result.exit_code == 0, (args, result.output)
        json.loads(result.output)
