"""Coding Lab resource access: prompts, workflows, checklists shared from one fetcher.

Sources:
- a local directory (e.g. a ``coding-lab`` checkout, or ``--source ./path``),
- a GitHub ``owner/repo`` (downloaded once, cached with a TTL).

Only Markdown files under the known resource directories are ever read.
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

from sklab.core import paths
from sklab.core.errors import (
    DOWNLOAD_FAILED,
    INVALID_ARCHIVE,
    NETWORK_ERROR,
    RESOURCE_NOT_FOUND,
    UNSAFE_ARCHIVE_PATH,
    SklabError,
)

RESOURCE_DIRS = ("prompts", "workflows", "agents", "checklists", "templates", "playbooks")

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_UNPACKED_BYTES = 150 * 1024 * 1024
MAX_FILES = 10_000


@dataclass
class ResourceInfo:
    name: str
    path: Path

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "path": str(self.path)}


class CodingLab:
    def __init__(
        self,
        source: str | None = None,
        *,
        branch: str = "main",
        timeout: int = 30,
        cache_ttl: int = 86400,
    ) -> None:
        self.source = (source or "sklabstudio/coding-lab").strip()
        self.branch = branch
        self.timeout = timeout
        self.cache_ttl = cache_ttl

    # -- resolution -----------------------------------------------------
    def is_local(self) -> bool:
        return Path(self.source).exists()

    def cache_root(self) -> Path:
        safe = self.source.replace("/", "__").replace(":", "_")
        root = paths.coding_lab_cache_dir() / f"{safe}__{self.branch}"
        return root

    def resolve(self, *, refresh: bool = False) -> Path:
        """Return a local directory containing the Coding Lab content."""
        if self.is_local():
            return Path(self.source).resolve()
        root = self.cache_root()
        if refresh:
            self.invalidate()
        if root.exists() and self._fresh(root):
            return root
        self._download_github(root)
        return root

    def invalidate(self) -> None:
        root = self.cache_root()
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)

    def _fresh(self, root: Path) -> bool:
        if self.cache_ttl <= 0:
            return True  # cached copy stays until explicit refresh
        try:
            age = time.time() - root.stat().st_mtime
        except OSError:
            return False
        return age < self.cache_ttl and any(root.iterdir())

    def describe(self) -> str:
        if self.is_local():
            return str(Path(self.source).resolve())
        return f"github:{self.source}@{self.branch} (cached)"

    # -- resources -------------------------------------------------------
    def list_resources(self, kind: str, *, refresh: bool = False) -> list[ResourceInfo]:
        base = self.resolve(refresh=refresh) / kind
        if not base.is_dir():
            return []
        items: list[ResourceInfo] = []
        for path in sorted(base.glob("*.md")):
            if path.is_file():
                items.append(ResourceInfo(name=path.stem, path=path))
        return items

    def list_prompts(self, *, refresh: bool = False) -> list[ResourceInfo]:
        return self.list_resources("prompts", refresh=refresh)

    def list_workflows(self, *, refresh: bool = False) -> list[ResourceInfo]:
        return self.list_resources("workflows", refresh=refresh)

    def get_resource(self, kind: str, name: str, *, refresh: bool = False) -> Path:
        base = self.resolve(refresh=refresh) / kind
        wanted = name.strip()
        if wanted.endswith(".md"):
            wanted = wanted[:-3]
        if not wanted or "/" in wanted or "\\" in wanted or ".." in wanted:
            raise SklabError(
                RESOURCE_NOT_FOUND,
                f"Resource not found: {name!r}.",
                remediation=f"Run 'sklab {kind}' to list available names.",
            )
        direct = base / f"{wanted}.md"
        if direct.is_file():
            return direct
        if base.is_dir():
            lowered = wanted.lower()
            for path in base.glob("*.md"):
                if path.stem.lower() == lowered:
                    return path
        available = [r.name for r in self.list_resources(kind)]
        hint = f" Available: {', '.join(available[:12])}." if available else ""
        raise SklabError(
            RESOURCE_NOT_FOUND,
            f"Resource not found: {name!r} (in {kind}/).{hint}",
            remediation=f"Run 'sklab {kind}' to list available names.",
        )

    def get_prompt(self, name: str, *, refresh: bool = False) -> Path:
        return self.get_resource("prompts", name, refresh=refresh)

    def get_workflow(self, name: str, *, refresh: bool = False) -> Path:
        return self.get_resource("workflows", name, refresh=refresh)

    def read_resource(self, kind: str, name: str, *, refresh: bool = False) -> str:
        path = self.get_resource(kind, name, refresh=refresh)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SklabError(RESOURCE_NOT_FOUND, f"Cannot read resource {name!r}: {exc}.") from exc

    # -- github fetch ----------------------------------------------------
    def _download_github(self, dest: Path) -> None:
        url = f"https://github.com/{self.source}/archive/refs/heads/{self.branch}.zip"
        try:
            with httpx.stream("GET", url, timeout=self.timeout, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise SklabError(
                        DOWNLOAD_FAILED,
                        f"Coding Lab download failed (HTTP {response.status_code}): {url}.",
                        remediation="Check the repository exists, or use --source with a local checkout.",
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise SklabError(DOWNLOAD_FAILED, "Coding Lab archive exceeds the download limit.")
                    chunks.append(chunk)
                data = b"".join(chunks)
        except SklabError:
            raise
        except httpx.TimeoutException as exc:
            raise SklabError(NETWORK_ERROR, f"Coding Lab download timed out after {self.timeout}s.") from exc
        except httpx.HTTPError as exc:
            raise SklabError(NETWORK_ERROR, f"Coding Lab download failed: {exc}.") from exc
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise SklabError(INVALID_ARCHIVE, "Downloaded Coding Lab archive is not a valid zip file.") from exc
        prefix = f"{self.source.split('/')[1]}-{self.branch}/" if "/" in self.source else ""
        with archive, tempfile.TemporaryDirectory(prefix="sklab-coding-lab-") as tmp:
            tmpdir = Path(tmp)
            unpacked = 0
            count = 0
            for member in archive.namelist():
                if prefix and not member.startswith(prefix):
                    continue
                rel_text = member[len(prefix):] if prefix else member
                if not rel_text or rel_text.endswith("/"):
                    continue
                top = PurePosixPath(rel_text).parts[0] if PurePosixPath(rel_text).parts else ""
                # Only known resource directories are materialized; top-level docs are skipped.
                if top not in RESOURCE_DIRS:
                    continue
                _assert_safe(rel_text)
                info = archive.getinfo(member)
                unpacked += info.file_size
                if unpacked > MAX_UNPACKED_BYTES:
                    raise SklabError(INVALID_ARCHIVE, "Coding Lab archive exceeds the unpack safety limit.")
                count += 1
                if count > MAX_FILES:
                    raise SklabError(INVALID_ARCHIVE, "Coding Lab archive contains too many files.")
                target = (tmpdir / PurePosixPath(rel_text)).resolve()
                try:
                    target.relative_to(tmpdir.resolve())
                except ValueError as exc:
                    raise SklabError(UNSAFE_ARCHIVE_PATH, f"Blocked unsafe archive entry: {member!r}.") from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, open(target, "wb") as fh:
                    shutil.copyfileobj(src, fh, length=1024 * 256)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(tmpdir), str(dest))


def _assert_safe(name: str) -> None:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or normalized.startswith(("/", "~")):
        raise SklabError(UNSAFE_ARCHIVE_PATH, f"Blocked unsafe archive entry: {name!r}.")
    if re.match(r"^[A-Za-z]:", normalized):
        raise SklabError(UNSAFE_ARCHIVE_PATH, f"Blocked unsafe archive entry: {name!r}.")
