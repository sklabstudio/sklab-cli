"""Local starter provider: copy starter directories from disk (offline-friendly)."""

from __future__ import annotations

import shutil
from pathlib import Path

from sklab.core.errors import STARTER_NOT_FOUND, SklabError
from sklab.starters.provider import STARTERS, StarterInfo, StarterProvider, require_starter

_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}


class LocalStarterProvider(StarterProvider):
    def __init__(self, root: Path) -> None:
        self.root = root

    def describe(self) -> str:
        return str(self.root)

    def list_starters(self) -> list[StarterInfo]:
        result: list[StarterInfo] = []
        for name, description in STARTERS.items():
            result.append(StarterInfo(name=name, description=description, available=(self.root / name).is_dir()))
        return result

    def starter_dir(self, starter: str) -> Path:
        key = require_starter(starter)
        candidate = self.root / key
        if not candidate.is_dir():
            raise SklabError(
                STARTER_NOT_FOUND,
                f"Starter {key!r} not found in local source: {self.root}.",
                remediation="Check --source points at a starters directory containing fullstack/, api/, frontend/.",
            )
        return candidate

    def iter_files(self, starter: str) -> list[str]:
        src = self.starter_dir(starter)
        rels: list[str] = []
        for path in sorted(src.rglob("*")):
            if any(part in _SKIP_DIRS for part in path.relative_to(src).parts):
                continue
            if path.is_file():
                rels.append(path.relative_to(src).as_posix())
        return rels

    def fetch(self, starter: str, dest: Path) -> list[str]:
        src = self.starter_dir(starter)
        dest.mkdir(parents=True, exist_ok=True)
        created: list[str] = []
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if any(part in _SKIP_DIRS for part in rel.parts):
                continue
            target = dest / rel
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                created.append(rel.as_posix())
        return created
