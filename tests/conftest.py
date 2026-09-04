"""Shared pytest fixtures: isolated config/cache, fixture paths, CLI runner."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
STARTER_FIXTURES = FIXTURES / "starters"
CODING_LAB_FIXTURES = FIXTURES / "coding-lab"
STACK_FIXTURES = FIXTURES / "stack-modules"


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate config/cache/stack-home locations.

    platformdirs on Windows resolves via CSIDL (ignoring XDG/APPDATA env),
    so sklab honors SKLAB_CONFIG_FILE / SKLAB_CACHE_DIR overrides, which the
    test-suite sets here. Stack state (``~/.sklab``) is isolated via
    SKLAB_HOME / SKLAB_MODULES_DIR / SKLAB_INSTALL_ROOT. Production code
    paths are unchanged.
    """
    home = tmp_path / "home"
    config_home = tmp_path / "config"
    cache_home = tmp_path / "cache"
    sklab_home = tmp_path / "sklab-home"
    for directory in (home, config_home, cache_home, sklab_home):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    # platformdirs on Windows honors APPDATA/LOCALAPPDATA.
    monkeypatch.setenv("APPDATA", str(config_home))
    monkeypatch.setenv("LOCALAPPDATA", str(cache_home))
    # Authoritative overrides honored by sklab.core.paths on every platform.
    monkeypatch.setenv("SKLAB_CONFIG_FILE", str(config_home / "config.toml"))
    monkeypatch.setenv("SKLAB_CACHE_DIR", str(cache_home / "sklab"))
    monkeypatch.setenv("NO_COLOR", "1")
    # Isolate the workstation stack home (never touch the real ~/.sklab in tests).
    monkeypatch.setenv("SKLAB_HOME", str(sklab_home))
    monkeypatch.delenv("SKLAB_MODULES_DIR", raising=False)
    monkeypatch.delenv("SKLAB_INSTALL_ROOT", raising=False)
    # Ensure no ambient SKLAB_* overrides leak in, except as tests set them.
    for key in (
        "SKLAB_STARTERS_SOURCE",
        "SKLAB_CODING_LAB_SOURCE",
        "SKLAB_DEFAULT_BRANCH",
        "SKLAB_NETWORK_TIMEOUT",
        "SKLAB_CACHE_TTL",
        "SKLAB_PRIVATE_MODULE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    _ = home
    _ = os.environ.get("HOME")
    return tmp_path


@pytest.fixture(autouse=True)
def _ample_disk_for_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic disk gate: real free disk varies per machine.

    Unit/integration tests must not depend on host free space; the gate's
    abort behavior is covered by its dedicated test, which overrides this stub.
    """
    from sklab.stack import preflight as _preflight

    monkeypatch.setattr(
        _preflight, "check_disk_ok", lambda required_mb, path=None: (True, "test override: ample disk")
    )


@pytest.fixture()
def starter_source() -> Path:
    return STARTER_FIXTURES


@pytest.fixture()
def coding_lab_source() -> Path:
    return CODING_LAB_FIXTURES
