"""Configuration: defaults <- config file (TOML) <- environment variables."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from sklab.core import paths
from sklab.core.errors import CONFIG_ERROR, SklabError

ENV_PREFIX = "SKLAB_"

DEFAULT_STARTERS_SOURCE = "sklabstudio/starters"
DEFAULT_CODING_LAB_SOURCE = "sklabstudio/coding-lab"
DEFAULT_BRANCH = "main"
DEFAULT_NETWORK_TIMEOUT = 30
DEFAULT_CACHE_TTL = 86400  # 24h in seconds


@dataclass
class SklabConfig:
    starters_source: str = DEFAULT_STARTERS_SOURCE
    coding_lab_source: str = DEFAULT_CODING_LAB_SOURCE
    default_branch: str = DEFAULT_BRANCH
    network_timeout: int = DEFAULT_NETWORK_TIMEOUT
    cache_ttl: int = DEFAULT_CACHE_TTL

    def to_dict(self) -> dict[str, object]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


KEYS = ("starters_source", "coding_lab_source", "default_branch", "network_timeout", "cache_ttl")


def _parse_int(value: str, key: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise SklabError(CONFIG_ERROR, f"Invalid integer for {key}: {value!r}.") from exc
    if parsed <= 0:
        raise SklabError(CONFIG_ERROR, f"Invalid value for {key}: must be a positive integer.")
    return parsed


def load_config(config_path: object = None) -> SklabConfig:
    """Load configuration without raising on a missing file.

    Raises SklabError(CONFIG_ERROR) on malformed files or values.
    """
    cfg = SklabConfig()
    path = paths.config_file() if config_path is None else Path(str(config_path))
    if path.exists():
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SklabError(CONFIG_ERROR, f"Cannot read config file: {path} ({exc}).") from exc
        except tomllib.TOMLDecodeError as exc:
            raise SklabError(CONFIG_ERROR, f"Invalid TOML in config file: {path} ({exc}).") from exc
        section = raw.get("sklab", raw) if isinstance(raw, dict) else {}
        if not isinstance(section, dict):
            raise SklabError(CONFIG_ERROR, f"Invalid config file structure: {path}.")
        for key in KEYS:
            if key in section:
                _apply_value(cfg, key, section[key], source=f"config file {path}")
    # Environment overrides win over the file.
    env_map = {
        "SKLAB_STARTERS_SOURCE": "starters_source",
        "SKLAB_CODING_LAB_SOURCE": "coding_lab_source",
        "SKLAB_DEFAULT_BRANCH": "default_branch",
        "SKLAB_NETWORK_TIMEOUT": "network_timeout",
        "SKLAB_CACHE_TTL": "cache_ttl",
    }
    for env_key, key in env_map.items():
        raw_value = os.environ.get(env_key)
        if raw_value is None or raw_value == "":
            continue
        if key in ("network_timeout", "cache_ttl"):
            _apply_value(cfg, key, _parse_int(raw_value.strip(), key), source=f"env {env_key}")
        else:
            _apply_value(cfg, key, raw_value.strip(), source=f"env {env_key}")
    return cfg


def _apply_value(cfg: SklabConfig, key: str, value: object, *, source: str) -> None:
    if key in ("network_timeout", "cache_ttl"):
        if isinstance(value, bool) or not isinstance(value, int):
            raise SklabError(CONFIG_ERROR, f"Invalid value for {key} from {source}: must be a positive integer.")
        if value <= 0:
            raise SklabError(CONFIG_ERROR, f"Invalid value for {key} from {source}: must be positive.")
        setattr(cfg, key, value)
        return
    if not isinstance(value, str) or not value.strip():
        raise SklabError(CONFIG_ERROR, f"Invalid value for {key} from {source}: must be a non-empty string.")
    setattr(cfg, key, value.strip())


def save_config(cfg: SklabConfig, config_path: object = None) -> object:
    """Persist configuration as simple TOML. Returns the path written."""
    path = paths.config_file() if config_path is None else Path(str(config_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[sklab]"]
    for key in KEYS:
        value = getattr(cfg, key)
        if isinstance(value, int):
            lines.append(f"{key} = {value}")
        else:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    lines.append("")
    try:
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        raise SklabError(CONFIG_ERROR, f"Cannot write config file: {path} ({exc}).") from exc
    return path


def set_value(key: str, value: str, config_path: object = None) -> SklabConfig:
    if key not in KEYS:
        raise SklabError(
            CONFIG_ERROR,
            f"Unknown config key: {key}.",
            remediation=f"Valid keys: {', '.join(KEYS)}.",
        )
    cfg = load_config(config_path)
    parsed: object = value
    if key in ("network_timeout", "cache_ttl"):
        parsed = _parse_int(value.strip(), key)
    _apply_value(cfg, key, parsed, source="command line")
    save_config(cfg, config_path)
    return cfg


def reset_config(config_path: object = None) -> SklabConfig:
    cfg = SklabConfig()
    save_config(cfg, config_path)
    return cfg
