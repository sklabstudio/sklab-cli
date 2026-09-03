"""Archive safety: zip-slip / traversal entries must be blocked."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from sklab.core.errors import SklabError
from sklab.starters.github import GitHubStarterProvider, assert_safe_member


@pytest.mark.parametrize(
    "name",
    ["../evil.txt", "/abs/path.txt", "a/../../evil.txt", "..\\windows.txt", "~/evil.txt"],
)
def test_assert_safe_member_rejects(name: str) -> None:
    with pytest.raises(SklabError) as exc_info:
        assert_safe_member(name)
    assert exc_info.value.code == "UNSAFE_ARCHIVE_PATH"


def test_assert_safe_member_accepts_normal() -> None:
    assert_safe_member("fullstack/README.md")


def _make_provider(monkeypatch: pytest.MonkeyPatch, payload: bytes, tmp_path) -> GitHubStarterProvider:  # type: ignore[no-untyped-def]
    provider = GitHubStarterProvider(repo="sklabstudio/starters", branch="main", timeout=5, cache_ttl=0)
    # Keep the (best-effort) archive cache inside the test tmp dir, never the real user cache.
    monkeypatch.setenv("SKLAB_CACHE_DIR", str(tmp_path / "test-cache"))

    class _Response:
        status_code = 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def iter_bytes(self, chunk_size: int = 65536):  # type: ignore[no-untyped-def]
            yield payload

    monkeypatch.setattr("sklab.starters.github.httpx.stream", lambda *a, **k: _Response())
    return provider


def test_github_fetch_blocks_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("starters-main/api/app.py", "print('hi')\n")
        archive.writestr("starters-main/api/../../evil.txt", "pwned\n")
    provider = _make_provider(monkeypatch, buf.getvalue(), tmp_path)
    with pytest.raises(SklabError) as exc_info:
        provider.fetch("api", tmp_path / "dest")
    assert exc_info.value.code in ("UNSAFE_ARCHIVE_PATH", "INVALID_ARCHIVE")
    assert not (tmp_path / "evil.txt").exists()


def test_github_fetch_extracts_only_starter_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("starters-main/api/app.py", "print('hi')\n")
        archive.writestr("starters-main/frontend/app.js", "console.log(1)\n")
    provider = _make_provider(monkeypatch, buf.getvalue(), tmp_path)
    created = provider.fetch("api", tmp_path / "dest")
    assert created == ["app.py"]
    assert (tmp_path / "dest" / "app.py").read_text() == "print('hi')\n"
    assert not (tmp_path / "dest" / "frontend").exists()
    assert "console.log" not in (tmp_path / "dest" / "app.py").read_text()


def test_github_fetch_invalid_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _make_provider(monkeypatch, b"not a zip file", tmp_path)
    with pytest.raises(SklabError) as exc_info:
        provider.fetch("api", tmp_path / "dest")
    assert exc_info.value.code == "INVALID_ARCHIVE"


def test_github_unknown_starter_never_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    class _Response:
        def __enter__(self):  # type: ignore[no-untyped-def]
            nonlocal called
            called = True
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr("sklab.starters.github.httpx.stream", lambda *a, **k: _Response())
    provider = GitHubStarterProvider(repo="sklabstudio/starters", branch="main", timeout=5, cache_ttl=0)
    with pytest.raises(SklabError) as exc_info:
        provider.fetch("nope", tmp_path / "dest")
    assert exc_info.value.code == "STARTER_NOT_FOUND"
    assert not called


def test_local_provider_missing_starter(tmp_path: Path) -> None:
    from sklab.starters.local import LocalStarterProvider

    with pytest.raises(SklabError) as exc_info:
        LocalStarterProvider(tmp_path).fetch("api", tmp_path / "dest")
    assert exc_info.value.code == "STARTER_NOT_FOUND"


def test_local_provider_roundtrip(starter_source: Path, tmp_path: Path) -> None:
    from sklab.starters.local import LocalStarterProvider

    provider = LocalStarterProvider(starter_source)
    created = provider.fetch("api", tmp_path / "dest")
    assert "README.md" in created
    assert (tmp_path / "dest" / "README.md").exists()
