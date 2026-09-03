"""Cache operations: status, clear, and the outside-dir guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from sklab.core.errors import SklabError
from sklab.resources.cache import SklabCache


def test_cache_status_empty(tmp_path: Path) -> None:
    cache = SklabCache(tmp_path / "cache")
    status = cache.status()
    assert status["exists"] is False
    assert status["files"] == 0


def test_cache_clear_only_inside(tmp_path: Path) -> None:
    root = tmp_path / "cache"
    (root / "coding-lab").mkdir(parents=True)
    (root / "coding-lab" / "x.md").write_text("hi")
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("do not delete")
    cache = SklabCache(root)
    result = cache.clear()
    assert result["removed_files"] >= 1
    assert sentinel.read_text() == "do not delete"
    assert root.exists()


def test_cache_guard_refuses_outside(tmp_path: Path) -> None:
    cache = SklabCache(tmp_path / "cache")
    with pytest.raises(SklabError):
        cache._guard(tmp_path / "elsewhere")


def test_cache_refresh_with_local_source(tmp_path: Path, coding_lab_source: Path) -> None:
    cache = SklabCache(tmp_path / "cache")
    result = cache.refresh(coding_lab_source=str(coding_lab_source))
    assert Path(str(result["coding_lab"])).exists()
