"""GitHub starter provider: download a repo archive, extract one starter directory.

Safety properties:
- no shell, httpx with timeouts, capped download size,
- zip-slip / path-traversal protection,
- per-file and total unpack limits,
- temporary files always cleaned up.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from sklab.core import paths
from sklab.core.errors import (
    DOWNLOAD_FAILED,
    INVALID_ARCHIVE,
    NETWORK_ERROR,
    UNSAFE_ARCHIVE_PATH,
    SklabError,
)
from sklab.starters.provider import STARTERS, StarterInfo, StarterProvider, require_starter

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 150 * 1024 * 1024
MAX_FILES = 10_000
MAX_FILE_BYTES = 20 * 1024 * 1024

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def parse_repo_source(source: str, default_branch: str = "main") -> tuple[str, str]:
    """Parse 'owner/repo', 'owner/repo@branch' or GitHub URLs into (repo, branch)."""
    text = source.strip()
    branch = default_branch
    if "@" in text and "://" not in text:
        text, _, maybe_branch = text.rpartition("@")
        if maybe_branch:
            branch = maybe_branch
    elif "://" in text:
        # https://github.com/owner/repo[/...][@branch]
        url_path = re.sub(r"^https?://[^/]+/", "", text).strip("/")
        url_path = re.sub(r"\.git$", "", url_path)
        parts = [p for p in url_path.split("/") if p not in ("", "archive", "tree", "blob", "refs", "heads")]
        if len(parts) >= 2:
            text = f"{parts[0]}/{parts[1]}"
            for i, part in enumerate(parts):
                if part in ("tree", "heads", "branch") and i + 1 < len(parts):
                    branch = parts[i + 1]
                    break
            else:
                if len(parts) >= 4 and parts[2] not in ("tree",):
                    branch = parts[3] if len(parts) > 3 else branch
        if "@" in text:
            text, _, maybe_branch = text.rpartition("@")
            if maybe_branch:
                branch = maybe_branch
    if not _REPO_RE.match(text):
        raise SklabError(
            DOWNLOAD_FAILED,
            f"Cannot parse starters source as a GitHub repository: {source!r}.",
            remediation="Use 'owner/repo', 'owner/repo@branch', a GitHub URL, or a local --source path.",
        )
    return text, branch


def archive_url(repo: str, branch: str) -> str:
    return f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"


def assert_safe_member(name: str) -> PurePosixPath:
    """Reject zip members that escape the destination (zip-slip protection)."""
    # Zip entries must use forward slashes; treat backslashes as separators too
    # so Windows-style traversal (``..\\evil``) is caught on every platform.
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts:
        raise SklabError(
            UNSAFE_ARCHIVE_PATH,
            f"Blocked unsafe archive entry: {name!r}.",
            remediation="The remote archive contains paths that escape the destination.",
        )
    # Windows drive letters / absolute paths / home expansion.
    if re.match(r"^[A-Za-z]:", normalized) or normalized.startswith(("/", "~")):
        raise SklabError(UNSAFE_ARCHIVE_PATH, f"Blocked unsafe archive entry: {name!r}.")
    return PurePosixPath(name)


class GitHubStarterProvider(StarterProvider):
    def __init__(self, repo: str, branch: str = "main", timeout: int = 30, cache_ttl: int = 86400) -> None:
        # Allow full GitHub URLs too; normalize to owner/repo + branch.
        if "://" in repo:
            repo, parsed_branch = parse_repo_source(repo, branch)
            branch = parsed_branch
        elif "@" in repo:
            repo, _, maybe_branch = repo.rpartition("@")
            if maybe_branch:
                branch = maybe_branch
        if not _REPO_RE.match(repo):
            raise SklabError(
                DOWNLOAD_FAILED,
                f"Cannot parse starters source as a GitHub repository: {repo!r}.",
                remediation="Use 'owner/repo', 'owner/repo@branch', a GitHub URL, or a local --source path.",
            )
        self.repo = repo
        self.branch = branch
        self.timeout = timeout
        self.cache_ttl = cache_ttl

    def describe(self) -> str:
        return f"github:{self.repo}@{self.branch}"

    def list_starters(self) -> list[StarterInfo]:
        # Listing via API would need auth/rate limits; the known starter set is stable.
        return [StarterInfo(name=n, description=d, available=True) for n, d in STARTERS.items()]

    def _cache_file(self) -> Path:
        safe = self.repo.replace("/", "__")
        paths.starters_cache_dir().mkdir(parents=True, exist_ok=True)
        return paths.starters_cache_dir() / f"{safe}__{self.branch}.zip"

    def _download(self) -> bytes:
        cached = self._cache_file()
        if cached.exists() and self.cache_ttl > 0:
            age = time.time() - cached.stat().st_mtime
            if age < self.cache_ttl:
                return cached.read_bytes()
        url = archive_url(self.repo, self.branch)
        try:
            with httpx.stream("GET", url, timeout=self.timeout, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise SklabError(
                        DOWNLOAD_FAILED,
                        f"Starter download failed (HTTP {response.status_code}): {url}.",
                        remediation="Check the repository and branch exist, or use --source with a local path.",
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise SklabError(
                            DOWNLOAD_FAILED,
                            f"Starter archive exceeds the {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB download limit.",
                            remediation="Use a local --source checkout instead.",
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
        except SklabError:
            raise
        except httpx.TimeoutException as exc:
            raise SklabError(
                NETWORK_ERROR,
                f"Starter download timed out after {self.timeout}s.",
                remediation="Retry later or use --source with a local path.",
            ) from exc
        except httpx.HTTPError as exc:
            raise SklabError(
                NETWORK_ERROR,
                f"Starter download failed: {exc}.",
                remediation="Check your connection or use --source with a local path.",
            ) from exc
        try:
            cached.write_bytes(data)
        except OSError:
            pass  # cache is best-effort
        return data

    def fetch(self, starter: str, dest: Path) -> list[str]:
        key = require_starter(starter)
        data = self._download()
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise SklabError(
                INVALID_ARCHIVE,
                "Downloaded starter archive is not a valid zip file.",
                remediation="Retry, or use --source with a local checkout.",
            ) from exc
        with archive:
            names = archive.namelist()
            if len(names) > MAX_FILES + 100:
                raise SklabError(INVALID_ARCHIVE, "Starter archive contains too many entries.")
            # GitHub prefixes entries with "<repo>-<branch>/".
            prefix_options = [f"{self.repo.split('/')[1]}-{self.branch}/{key}/"]
            matched = [n for n in names if any(n.startswith(p) for p in prefix_options)]
            if not matched:
                # Fallback: some archives differ; accept any "<something>/<starter>/" prefix.
                matched = [n for n in names if f"/{key}/" in ("/" + n)]
                prefix_options = []
            if not matched:
                raise SklabError(
                    INVALID_ARCHIVE,
                    f"Starter {key!r} not found in archive {self.repo}@{self.branch}.",
                    remediation="Check the starters repository layout (fullstack/, api/, frontend/).",
                )
            dest.mkdir(parents=True, exist_ok=True)
            created: list[str] = []
            total = 0
            count = 0
            with tempfile.TemporaryDirectory(prefix="sklab-starter-") as tmp:
                tmpdir = Path(tmp)
                for name in matched:
                    assert_safe_member(name)
                    # Strip the "<top>/<starter>/" prefix to get the relative path.
                    if prefix_options:
                        rel_text = name[len(prefix_options[0]):]
                    else:
                        idx = ("/" + name).find(f"/{key}/")
                        rel_text = name[idx + len(key) + 2 :]
                    if not rel_text or rel_text.endswith("/"):
                        continue
                    rel_pure = assert_safe_member(rel_text)
                    info = archive.getinfo(name)
                    size = info.file_size
                    if size > MAX_FILE_BYTES:
                        raise SklabError(
                            INVALID_ARCHIVE,
                            f"Starter archive entry too large: {rel_text!r}.",
                        )
                    total += size
                    if total > MAX_UNPACKED_BYTES:
                        raise SklabError(
                            INVALID_ARCHIVE,
                            "Starter archive unpacked size exceeds the safety limit.",
                        )
                    count += 1
                    if count > MAX_FILES:
                        raise SklabError(INVALID_ARCHIVE, "Starter archive contains too many files.")
                    target = (tmpdir / rel_pure).resolve()
                    try:
                        target.relative_to(tmpdir.resolve())
                    except ValueError as exc:
                        raise SklabError(UNSAFE_ARCHIVE_PATH, f"Blocked unsafe archive entry: {name!r}.") from exc
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as src, open(target, "wb") as fh:
                        shutil.copyfileobj(src, fh, length=1024 * 256)
                # Stage is safe; move into dest.
                for path in sorted(tmpdir.rglob("*")):
                    if path.is_file():
                        rel = path.relative_to(tmpdir)
                        final = dest / rel
                        final.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, final)
                        created.append(rel.as_posix())
            return created
