"""Filesystem locations for config and cache (cross-platform via platformdirs)."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

APP_NAME = "sklab"


def config_dir() -> Path:
    override = os.environ.get("SKLAB_CONFIG_DIR")
    if override:
        return Path(override)
    return Path(user_config_dir(APP_NAME))


def config_file() -> Path:
    override = os.environ.get("SKLAB_CONFIG_FILE")
    if override:
        return Path(override)
    return config_dir() / "config.toml"


def cache_dir() -> Path:
    override = os.environ.get("SKLAB_CACHE_DIR")
    if override:
        return Path(override)
    return Path(user_cache_dir(APP_NAME))


def coding_lab_cache_dir() -> Path:
    return cache_dir() / "coding-lab"


def starters_cache_dir() -> Path:
    return cache_dir() / "starters"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    cache_dir().mkdir(parents=True, exist_ok=True)
