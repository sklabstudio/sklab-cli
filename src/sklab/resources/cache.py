"""Local cache management. Everything lives under the platformdirs cache dir.

Never deletes anything outside the SKLab cache directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from sklab.core import paths
from sklab.core.errors import CACHE_ERROR, SklabError


class CacheStatus(TypedDict):
    location: str
    exists: bool
    size_bytes: int
    files: int
    entries: list[str]


class CacheClearResult(TypedDict):
    location: str
    removed_files: int


class SklabCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or paths.cache_dir()

    def _guard(self, path: Path) -> Path:
        resolved_root = self.root.resolve()
        resolved = path.resolve()
        if resolved != resolved_root and resolved_root not in resolved.parents:
            raise SklabError(CACHE_ERROR, f"Refusing to operate outside the cache directory: {path}.")
        return resolved

    def status(self) -> CacheStatus:
        root = self.root
        total_bytes = 0
        files = 0
        entries: list[str] = []
        if root.exists():
            for child in sorted(root.iterdir()):
                entries.append(child.name)
                if child.is_file():
                    files += 1
                    try:
                        total_bytes += child.stat().st_size
                    except OSError:
                        pass
                elif child.is_dir():
                    for path in child.rglob("*"):
                        if path.is_file():
                            files += 1
                            try:
                                total_bytes += path.stat().st_size
                            except OSError:
                                pass
        return {
            "location": str(root),
            "exists": root.exists(),
            "size_bytes": total_bytes,
            "files": files,
            "entries": entries,
        }

    def clear(self) -> CacheClearResult:
        root = self._guard(self.root)
        removed_files = 0
        if root.exists():
            for child in list(root.iterdir()):
                target = self._guard(child)
                if target.is_file() or target.is_symlink():
                    try:
                        target.unlink()
                        removed_files += 1
                    except OSError:
                        pass
                elif target.is_dir():
                    removed_files += _rmtree_contents(target)
                    try:
                        target.rmdir()
                    except OSError:
                        pass
        root.mkdir(parents=True, exist_ok=True)
        return {"location": str(self.root), "removed_files": removed_files}

    def refresh(
        self, coding_lab_source: str | None = None, timeout: int = 30, cache_ttl: int = 86400
    ) -> dict[str, object]:
        """Drop cached Coding Lab content and re-resolve it (works offline for local sources)."""
        from sklab.resources.coding_lab import CodingLab

        lab = CodingLab(source=coding_lab_source, timeout=timeout, cache_ttl=cache_ttl)
        lab.invalidate()
        resolved = lab.resolve()
        return {"location": str(self.root), "coding_lab": str(resolved)}


def _rmtree_contents(directory: Path) -> int:
    removed = 0
    for child in list(directory.iterdir()):
        if child.is_file() or child.is_symlink():
            try:
                child.unlink()
                removed += 1
            except OSError:
                pass
        elif child.is_dir():
            removed += _rmtree_contents(child)
            try:
                child.rmdir()
            except OSError:
                pass
    return removed
