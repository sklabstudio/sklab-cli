"""Config loading, env overrides, persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from sklab.core import paths
from sklab.core.config import SklabConfig, load_config, reset_config, save_config, set_value
from sklab.core.errors import SklabError


def test_defaults_without_file(isolated_home: Path) -> None:
    cfg = load_config()
    assert cfg.starters_source == "sklabstudio/starters"
    assert cfg.coding_lab_source == "sklabstudio/coding-lab"
    assert cfg.default_branch == "main"
    assert cfg.network_timeout == 30
    assert cfg.cache_ttl == 86400


def test_env_overrides(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKLAB_STARTERS_SOURCE", "./local-starters")
    monkeypatch.setenv("SKLAB_NETWORK_TIMEOUT", "7")
    cfg = load_config()
    assert cfg.starters_source == "./local-starters"
    assert cfg.network_timeout == 7


def test_env_invalid_int(isolated_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKLAB_NETWORK_TIMEOUT", "not-a-number")
    with pytest.raises(SklabError) as exc_info:
        load_config()
    assert exc_info.value.code == "CONFIG_ERROR"


def test_save_load_roundtrip(isolated_home: Path) -> None:
    cfg = SklabConfig(starters_source="./x", network_timeout=11)
    target = save_config(cfg)
    assert target == paths.config_file()
    loaded = load_config()
    assert loaded.starters_source == "./x"
    assert loaded.network_timeout == 11


def test_set_rejects_unknown_key(isolated_home: Path) -> None:
    with pytest.raises(SklabError) as exc_info:
        set_value("nope", "x")
    assert exc_info.value.code == "CONFIG_ERROR"


def test_set_and_reset(isolated_home: Path) -> None:
    set_value("network_timeout", "42")
    assert load_config().network_timeout == 42
    reset_config()
    assert load_config().network_timeout == 30


def test_malformed_toml_raises(isolated_home: Path) -> None:
    path = paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[sklab\nbroken", encoding="utf-8")
    with pytest.raises(SklabError) as exc_info:
        load_config()
    assert exc_info.value.code == "CONFIG_ERROR"
