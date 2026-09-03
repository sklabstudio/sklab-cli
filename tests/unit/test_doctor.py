"""Repository detection and doctor checks (offline, read-only)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sklab.diagnostics.checks import run_doctor
from sklab.diagnostics.detector import detect_project
from sklab.diagnostics.models import CheckStatus
from tests.conftest import FIXTURES


def _by_id(checks, check_id: str):  # type: ignore[no-untyped-def]
    for check in checks:
        if check.id == check_id:
            return check
    raise AssertionError(f"missing check {check_id}")


def test_detect_python_only() -> None:
    info = detect_project(FIXTURES / "projects" / "python-only")
    assert info.has_python
    assert not info.has_node


def test_detect_node_only() -> None:
    info = detect_project(FIXTURES / "projects" / "node-only")
    assert info.has_node
    assert not info.has_python
    assert "test" in info.node_scripts


def test_detect_mixed() -> None:
    info = detect_project(FIXTURES / "projects" / "mixed")
    assert info.has_python and info.has_node


def test_doctor_python_project_passes_python_and_skips_node() -> None:
    _info, checks = run_doctor(FIXTURES / "projects" / "python-only")
    assert _by_id(checks, "python").status == CheckStatus.PASS
    assert _by_id(checks, "node").status == CheckStatus.SKIPPED


def test_doctor_node_project_checks_node() -> None:
    _info, checks = run_doctor(FIXTURES / "projects" / "node-only")
    node = _by_id(checks, "node")
    # Node may or may not be installed on the test machine; either way it must adapt.
    assert node.status in (CheckStatus.PASS, CheckStatus.FAIL)
    assert _by_id(checks, "python").status == CheckStatus.SKIPPED


def test_doctor_mixed_project_checks_both() -> None:
    _info, checks = run_doctor(FIXTURES / "projects" / "mixed")
    assert _by_id(checks, "python").status == CheckStatus.PASS
    assert _by_id(checks, "node").status in (CheckStatus.PASS, CheckStatus.FAIL)


def test_doctor_docker_skipped_without_docker_files(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hi")
    _info, checks = run_doctor(tmp_path)
    assert _by_id(checks, "docker").status in (CheckStatus.PASS, CheckStatus.SKIPPED)
    assert _by_id(checks, "docker-compose").status == CheckStatus.SKIPPED


def test_doctor_is_read_only(tmp_path: Path) -> None:
    before = {p.name for p in tmp_path.iterdir()}
    run_doctor(tmp_path)
    after = {p.name for p in tmp_path.iterdir()}
    assert before == after


def test_doctor_env_warning(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("KEY=")
    _info, checks = run_doctor(tmp_path)
    env = _by_id(checks, "env-file")
    assert env.status == CheckStatus.WARNING
    assert env.remediation


def test_doctor_git_status_dirty(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=False)  # noqa: S603
    (tmp_path / "file.txt").write_text("x")
    _info, checks = run_doctor(tmp_path)
    assert _by_id(checks, "git-status").status == CheckStatus.WARNING
