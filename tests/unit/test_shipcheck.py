"""Shipcheck planning, timeouts, verdicts, and exit codes."""

from __future__ import annotations

import sys
from pathlib import Path

from sklab.core.subprocess import run_command
from sklab.diagnostics.detector import detect_project
from sklab.diagnostics.models import CheckResult, CheckStatus
from sklab.release.models import Verdict, exit_code_for
from sklab.release.planner import build_plan
from sklab.release.runner import _verdict_for, run_shipcheck
from tests.conftest import FIXTURES


def test_exit_codes() -> None:
    assert exit_code_for(Verdict.READY) == 0
    assert exit_code_for(Verdict.READY_WITH_WARNINGS) == 1
    assert exit_code_for(Verdict.NOT_READY) == 2


def test_verdict_computation() -> None:
    def _check(status: CheckStatus) -> CheckResult:
        return CheckResult(id="x", name="X", status=status, message="m")

    assert _verdict_for([_check(CheckStatus.PASS)]) == Verdict.READY
    assert _verdict_for([_check(CheckStatus.PASS), _check(CheckStatus.WARNING)]) == Verdict.READY_WITH_WARNINGS
    assert _verdict_for([_check(CheckStatus.UNKNOWN)]) == Verdict.READY_WITH_WARNINGS
    assert _verdict_for([_check(CheckStatus.WARNING), _check(CheckStatus.FAIL)]) == Verdict.NOT_READY


def test_plan_python_only_has_pytest_not_npm() -> None:
    info = detect_project(FIXTURES / "projects" / "python-only")
    ids = [s.id for s in build_plan(info)]
    assert "git-status" in ids
    assert "node-test" not in ids and "node-build" not in ids


def test_plan_node_only_discovers_real_scripts() -> None:
    info = detect_project(FIXTURES / "projects" / "node-only")
    ids = [s.id for s in build_plan(info)]
    assert "node-test" in ids
    assert "node-lint" in ids
    assert "node-build" in ids
    assert "python-tests" not in ids


def test_plan_mixed_without_test_script_has_no_node_test() -> None:
    info = detect_project(FIXTURES / "projects" / "mixed")
    ids = [s.id for s in build_plan(info)]
    assert "node-test" not in ids  # mixed fixture has only a build script
    assert "node-build" in ids


def test_plan_never_invents_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "x", "scripts": {}}', encoding="utf-8")
    info = detect_project(tmp_path)
    ids = [s.id for s in build_plan(info)]
    assert "node-test" not in ids and "node-lint" not in ids and "node-build" not in ids


def test_plan_always_includes_inspections(tmp_path: Path) -> None:
    info = detect_project(tmp_path)
    ids = [s.id for s in build_plan(info)]
    assert "env-docs" in ids and "readme" in ids


def test_command_timeout_handling() -> None:
    result = run_command(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout=0.5,
    )
    assert result.timed_out
    assert not result.ok


def test_missing_binary_reports_not_found() -> None:
    result = run_command(["sklab-definitely-missing-binary-xyz"], timeout=5.0)
    assert result.not_found
    assert not result.ok


def test_shipcheck_runs_offline_on_empty_dir(tmp_path: Path) -> None:
    report = run_shipcheck(tmp_path, timeout_per_command=30.0)
    assert report.verdict in (Verdict.READY, Verdict.READY_WITH_WARNINGS, Verdict.NOT_READY)
    assert report.duration_ms >= 0
    assert {c.id for c in report.checks} >= {"git-status", "env-docs", "readme"}


def test_shipcheck_report_serializes() -> None:
    import json

    report = run_shipcheck(Path(FIXTURES / "projects" / "python-only"), timeout_per_command=30.0)
    payload = json.loads(report.model_dump_json())
    assert payload["verdict"] in ("READY", "READY_WITH_WARNINGS", "NOT_READY")
    assert isinstance(payload["checks"], list)
