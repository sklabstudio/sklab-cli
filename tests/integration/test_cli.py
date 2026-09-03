"""End-to-end CLI tests through Typer's CliRunner (no network)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from sklab import __version__
from sklab.cli import app
from tests.conftest import FIXTURES


def _invoke(runner: CliRunner, *args: str, env: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    return runner.invoke(app, list(args), env=env)


def test_version(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_commands(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "--help")
    assert result.exit_code == 0
    for command in ("init", "doctor", "shipcheck", "starters", "prompts", "prompt", "config", "cache", "info"):
        assert command in result.output


def test_starters_json(runner: CliRunner, isolated_home: Path, starter_source: Path) -> None:
    result = _invoke(runner, "starters", "--json", "--source", str(starter_source))
    assert result.exit_code == 0
    payload = json.loads(result.output)
    names = {s["name"] for s in payload["starters"]}
    assert {"fullstack", "api", "frontend"} <= names


def test_starters_table(runner: CliRunner, isolated_home: Path, starter_source: Path) -> None:
    result = _invoke(runner, "starters", "--source", str(starter_source))
    assert result.exit_code == 0
    assert "fullstack" in result.output


def test_init_dry_run(runner: CliRunner, isolated_home: Path, starter_source: Path, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = _invoke(runner, "init", "fullstack", "demo", "--dry-run", "--source", str(starter_source))
    assert result.exit_code == 0
    assert not (tmp_path / "demo").exists()
    assert "Dry run" in result.output


def test_init_unknown_starter(runner: CliRunner, isolated_home: Path, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = _invoke(runner, "init", "nope", "demo")
    assert result.exit_code != 0
    assert "STARTER_NOT_FOUND" in result.output


def test_init_local_full_cycle(runner: CliRunner, isolated_home: Path, starter_source: Path, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = _invoke(runner, "init", "api", "my-api", "--source", str(starter_source))
    assert result.exit_code == 0, result.output
    dest = tmp_path / "my-api"
    assert (dest / "README.md").exists()
    content = (dest / "README.md").read_text(encoding="utf-8")
    assert "{{PROJECT_NAME}}" not in content
    assert "my-api" in content


def test_init_protects_existing(runner: CliRunner, isolated_home: Path, starter_source: Path, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "precious.txt").write_text("user data")
    result = _invoke(runner, "init", "api", "taken", "--source", str(starter_source))
    assert result.exit_code != 0
    assert "DESTINATION_EXISTS" in result.output
    assert (tmp_path / "taken" / "precious.txt").read_text() == "user data"


def test_init_json_valid(runner: CliRunner, isolated_home: Path, starter_source: Path, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = _invoke(runner, "init", "frontend", "site", "--source", str(starter_source), "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["project"] == "site"


def test_doctor_json_valid(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "doctor", "--path", str(FIXTURES / "projects" / "mixed"), "--json")
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "checks" in payload
    statuses = {c["status"] for c in payload["checks"]}
    assert statuses <= {"PASS", "WARNING", "FAIL", "SKIPPED", "UNKNOWN"}


def test_doctor_table(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "doctor", "--path", str(FIXTURES / "projects" / "python-only"))
    assert result.exit_code == 0
    assert "SKLab Doctor" in result.output


def test_shipcheck_dry_run(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "shipcheck", "--path", str(FIXTURES / "projects" / "mixed"), "--dry-run")
    assert result.exit_code == 0
    assert "Planned checks" in result.output


def test_shipcheck_json_exit_codes(runner: CliRunner, isolated_home: Path, tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hi")
    result = _invoke(runner, "shipcheck", "--path", str(tmp_path), "--json")
    payload = json.loads(result.output)
    assert payload["verdict"] in ("READY", "READY_WITH_WARNINGS", "NOT_READY")
    assert result.exit_code in (0, 1, 2)


def test_prompts_and_workflows(runner: CliRunner, isolated_home: Path, coding_lab_source: Path) -> None:
    result = _invoke(runner, "prompts", "--source", str(coding_lab_source))
    assert result.exit_code == 0
    assert "audit-repository" in result.output
    result = _invoke(runner, "workflows", "--source", str(coding_lab_source))
    assert result.exit_code == 0
    assert "repo-rescue" in result.output


def test_prompt_stdout_and_output(runner: CliRunner, isolated_home: Path, coding_lab_source: Path, tmp_path: Path) -> None:
    result = _invoke(runner, "prompt", "audit-repository", "--source", str(coding_lab_source))
    assert result.exit_code == 0
    assert "Audit Repository" in result.output
    target = tmp_path / "audit.md"
    result = _invoke(runner, "prompt", "audit-repository", "--source", str(coding_lab_source), "--output", str(target))
    assert result.exit_code == 0
    assert "Audit Repository" in target.read_text(encoding="utf-8")


def test_workflow_stdout(runner: CliRunner, isolated_home: Path, coding_lab_source: Path) -> None:
    result = _invoke(runner, "workflow", "repo-rescue", "--source", str(coding_lab_source))
    assert result.exit_code == 0
    assert "Repo Rescue" in result.output


def test_prompt_missing(runner: CliRunner, isolated_home: Path, coding_lab_source: Path) -> None:
    result = _invoke(runner, "prompt", "missing-thing", "--source", str(coding_lab_source))
    assert result.exit_code != 0
    assert "RESOURCE_NOT_FOUND" in result.output


def test_config_show_and_set(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "config", "show")
    assert result.exit_code == 0
    assert "starters_source" in result.output
    result = _invoke(runner, "config", "set", "network_timeout", "17")
    assert result.exit_code == 0
    result = _invoke(runner, "config", "get", "network_timeout")
    assert result.exit_code == 0
    assert "17" in result.output


def test_config_env_override(runner: CliRunner, isolated_home: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SKLAB_NETWORK_TIMEOUT", "9")
    result = _invoke(runner, "config", "show", "--json")
    assert result.exit_code == 0
    assert json.loads(result.output)["network_timeout"] == 9


def test_cache_status_and_clear(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "cache", "status", "--json")
    assert result.exit_code == 0
    assert "location" in json.loads(result.output)
    result = _invoke(runner, "cache", "clear", "--yes")
    assert result.exit_code == 0


def test_info(runner: CliRunner, isolated_home: Path) -> None:
    result = _invoke(runner, "info")
    assert result.exit_code == 0
    assert __version__ in result.output
    result = _invoke(runner, "info", "--json")
    assert result.exit_code == 0
    assert json.loads(result.output)["sklab"] == __version__


def test_version_matches_pyproject() -> None:
    import tomllib

    root = Path(__file__).resolve().parents[2]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__
