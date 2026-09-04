"""Regression: setup re-runs must refresh module code, never no-op with success.

Live-VPS finding: bare `pipx install <dir>` exits 0 without touching an
existing venv ("already seems to be installed"), and plain
`pip install <dir>` is a same-version no-op ("already satisfied"). Both once
left stale module code in place while setup reported READY.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sklab.core.subprocess import CommandResult
from sklab.stack import adapters
from sklab.stack.adapters import AdapterResult
from sklab.stack.manifest import ModuleManifest


def _manifest() -> ModuleManifest:
    return ModuleManifest.model_validate({
        "schema_version": 1,
        "id": "refresh-probe",
        "name": "Refresh Probe",
        "version": "0.1.0",
        "visibility": "public",
        "source": {"type": "git", "repository": "sklabstudio/refresh-probe"},
        "install": {"type": "python", "package_path": "."},
        "health": {"command": ["refresh-probe", "--version"]},
    })


@pytest.fixture()
def checkout_repo(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fake a checked-out python project; patch out the git step (no network)."""
    repo = isolated_home / "sklab-home" / "repos" / "refresh-probe"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text(
        "[project]\nname = \"refresh-probe\"\nversion = \"0.1.0\"\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        adapters, "_git_checkout",
        lambda manifest, **kwargs: AdapterResult(
            module_id=manifest.id, ok=True, status="READY",
            message="test checkout", steps=[], changed=True),
    )
    return repo


def _fake_ok(calls: list) -> object:
    def fake_run(argv: list[str], **kwargs: object) -> CommandResult:
        calls.append(list(argv))
        return CommandResult(argv=list(argv), returncode=0, stdout="ok", stderr="")
    return fake_run


def test_pipx_install_forces_refresh(
    monkeypatch: pytest.MonkeyPatch, checkout_repo: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(adapters, "run_command", _fake_ok(calls))
    monkeypatch.setattr(
        adapters.shutil, "which",
        lambda name: "/usr/bin/pipx" if name == "pipx" else None,
    )
    res = adapters._install_python(_manifest(), timeout=10.0)
    assert res.ok, res.message
    pipx_calls = [c for c in calls if c[:2] == ["/usr/bin/pipx", "install"]]
    assert pipx_calls, calls
    assert "--force" in pipx_calls[0], pipx_calls[0]
    assert str(checkout_repo) in pipx_calls[0]


def test_venv_fallback_forces_reinstall(
    monkeypatch: pytest.MonkeyPatch, checkout_repo: Path,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(adapters, "run_command", _fake_ok(calls))
    monkeypatch.setattr(adapters.shutil, "which", lambda name: None)
    res = adapters._install_python(_manifest(), timeout=10.0)
    assert res.ok, res.message
    pip_calls = [c for c in calls if c[0].endswith("pip") or c[0].endswith("pip.exe")]
    assert pip_calls, calls
    assert "--force-reinstall" in pip_calls[0], pip_calls[0]
    assert str(checkout_repo) in pip_calls[0]
