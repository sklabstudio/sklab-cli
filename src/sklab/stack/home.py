"""SKLab workstation home: ``~/.sklab`` layout (separate from platformdirs config/cache)."""

from __future__ import annotations

import os
from pathlib import Path


def sklab_home() -> Path:
    override = os.environ.get("SKLAB_HOME")
    if override:
        return Path(override)
    return Path.home() / ".sklab"


def config_root() -> Path:
    return sklab_home() / "config"


def modules_dir() -> Path:
    override = os.environ.get("SKLAB_MODULES_DIR")
    if override:
        return Path(override)
    return sklab_home() / "modules.d"


def state_dir() -> Path:
    return sklab_home() / "state"


def logs_dir() -> Path:
    return sklab_home() / "logs"


def cache_root() -> Path:
    return sklab_home() / "cache"


def install_root() -> Path:
    override = os.environ.get("SKLAB_INSTALL_ROOT")
    if override:
        return Path(override)
    return sklab_home() / "modules"


def state_file() -> Path:
    return state_dir() / "install-state.json"


def ensure_layout() -> dict[str, object]:
    created: list[str] = []
    for directory in (config_root(), modules_dir(), state_dir(), logs_dir(), cache_root(), install_root()):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created.append(str(directory))
        else:
            directory.mkdir(parents=True, exist_ok=True)
    return {"home": str(sklab_home()), "created": created}
