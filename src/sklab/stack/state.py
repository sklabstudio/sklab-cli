"""Atomic installer state: installed modules, versions, fingerprints, health."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sklab.stack import home as stack_home


@dataclass
class ModuleRecord:
    id: str
    version: str = ""
    install_type: str = ""
    origin: str = ""
    manifest_fingerprint: str = ""
    source_fingerprint: str = ""
    last_health: str = ""
    last_updated: str = ""
    status: str = ""


@dataclass
class InstallerState:
    modules: dict[str, ModuleRecord] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": self.updated_at,
            "modules": {
                mid: {
                    "id": rec.id,
                    "version": rec.version,
                    "install_type": rec.install_type,
                    "origin": rec.origin,
                    "manifest_fingerprint": rec.manifest_fingerprint,
                    "source_fingerprint": rec.source_fingerprint,
                    "last_health": rec.last_health,
                    "last_updated": rec.last_updated,
                    "status": rec.status,
                }
                for mid, rec in sorted(self.modules.items())
            },
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_state(path: Path | None = None) -> InstallerState:
    location = path or stack_home.state_file()
    if not location.exists():
        return InstallerState()
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return InstallerState()
    state = InstallerState(updated_at=str(raw.get("updated_at", "")))
    modules = raw.get("modules", {})
    if isinstance(modules, dict):
        for mid, item in modules.items():
            if not isinstance(item, dict):
                continue
            state.modules[mid] = ModuleRecord(
                id=str(item.get("id", mid)),
                version=str(item.get("version", "")),
                install_type=str(item.get("install_type", "")),
                origin=str(item.get("origin", "")),
                manifest_fingerprint=str(item.get("manifest_fingerprint", "")),
                source_fingerprint=str(item.get("source_fingerprint", "")),
                last_health=str(item.get("last_health", "")),
                last_updated=str(item.get("last_updated", "")),
                status=str(item.get("status", "")),
            )
    return state


def save_state(state: InstallerState, path: Path | None = None) -> Path:
    location = path or stack_home.state_file()
    location.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = _now()
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True)
    # Atomic write: temp file in the same directory, then os.replace.
    fd, tmp_name = tempfile.mkstemp(dir=str(location.parent), prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        os.replace(tmp_name, location)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass
    return location


def record_module(
    state: InstallerState,
    *,
    module_id: str,
    version: str,
    install_type: str,
    origin: str,
    manifest_fingerprint: str,
    source_fingerprint: str = "",
    status: str = "",
    health: str = "",
) -> None:
    state.modules[module_id] = ModuleRecord(
        id=module_id,
        version=version,
        install_type=install_type,
        origin=origin,
        manifest_fingerprint=manifest_fingerprint,
        source_fingerprint=source_fingerprint,
        last_health=health,
        last_updated=_now(),
        status=status,
    )
