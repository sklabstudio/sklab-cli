"""SKLab workstation home and install roots.

v0.2 layout (preserved, backward compatible)::

    ~/.sklab/  (SKLAB_HOME overrides)
      config/ modules.d/ state/ logs/ cache/ modules/

v0.3 adds a stable *system* install root for real checkouts and runtime::

    root:     /opt/sklab/{repos,runtime,logs}
    non-root: ~/.local/share/sklab/{repos,runtime,logs}  (XDG equivalent)

Repository checkouts and generated runtime state are always separated.
Nothing is scattered randomly across $HOME.
"""

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
    for directory in (
        config_root(), modules_dir(), state_dir(), logs_dir(), cache_root(),
        install_root(), repos_dir(), runtime_dir(), system_logs_dir(), venvs_dir(),
    ):
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=True)
            created.append(str(directory))
        else:
            directory.mkdir(parents=True, exist_ok=True)
    return {"home": str(sklab_home()), "created": created}


# --- v0.3 system roots -----------------------------------------------------


def is_root() -> bool:
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def system_root() -> Path:
    """Stable install location: /opt/sklab for root, XDG data dir otherwise.

    SKLAB_SYSTEM_ROOT overrides (tests/automation). SKLAB_INSTALL_ROOT still
    overrides install_root() for full backward compatibility.
    """
    override = os.environ.get("SKLAB_SYSTEM_ROOT")
    if override:
        return Path(override)
    if is_root():
        return Path("/opt/sklab")
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "sklab"
    return Path.home() / ".local" / "share" / "sklab"


def repos_dir() -> Path:
    """Where git checkouts live. SKLAB_REPOS_DIR overrides."""
    override = os.environ.get("SKLAB_REPOS_DIR")
    if override:
        return Path(override)
    # Keep v0.2 hermeticity: under SKLAB_HOME when it is explicitly set
    # (tests/CI), otherwise under the stable system root.
    if os.environ.get("SKLAB_HOME"):
        return sklab_home() / "repos"
    return system_root() / "repos"


def runtime_dir() -> Path:
    override = os.environ.get("SKLAB_RUNTIME_DIR")
    if override:
        return Path(override)
    if os.environ.get("SKLAB_HOME"):
        return sklab_home() / "runtime"
    return system_root() / "runtime"


def system_logs_dir() -> Path:
    if os.environ.get("SKLAB_HOME"):
        return logs_dir()
    return system_root() / "logs"


def venvs_dir() -> Path:
    if os.environ.get("SKLAB_HOME"):
        return sklab_home() / "venvs"
    return runtime_dir() / "venvs"
