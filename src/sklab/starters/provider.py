"""Starter provider abstraction: local directories today, GitHub archives tomorrow-proof."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from sklab.core.errors import (
    DESTINATION_EXISTS,
    INVALID_PROJECT_NAME,
    STARTER_NOT_FOUND,
    UNSAFE_PATH,
    SklabError,
)

#: Known starters with theirshort descriptions (shown by ``sklab starters``).
STARTERS: dict[str, str] = {
    "fullstack": "Next.js + FastAPI + PostgreSQL",
    "api": "FastAPI + PostgreSQL",
    "frontend": "Next.js + TypeScript",
}

_PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,213}$")

# Windows-reserved device names (checked case-insensitively, without extension).
_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


@dataclass
class StarterInfo:
    name: str
    description: str
    available: bool = True


def validate_project_name(name: str) -> str:
    """Validate a project name; returns the name or raises SklabError."""
    if not name or not name.strip():
        raise SklabError(
            INVALID_PROJECT_NAME,
            "Project name must not be empty.",
            remediation="Use a plain directory name such as 'my-app'.",
        )
    name = name.strip()
    if "/" in name or "\\" in name or name in (".", "..") or ".." in Path(name).parts:
        raise SklabError(
            UNSAFE_PATH,
            f"Unsafe project name: {name!r}.",
            remediation="Use a plain directory name without path separators (e.g. 'my-app').",
        )
    if not _PROJECT_NAME_RE.match(name):
        raise SklabError(
            INVALID_PROJECT_NAME,
            f"Invalid project name: {name!r}.",
            remediation="Use 1-214 chars: letters, digits, '.', '_' or '-', starting with a letter or digit.",
        )
    stem = name.split(".")[0].lower()
    if stem in _RESERVED_NAMES:
        raise SklabError(
            INVALID_PROJECT_NAME,
            f"Reserved project name: {name!r}.",
            remediation="Choose a different project name.",
        )
    return name


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "app"


def resolve_destination(name: str, cwd: Path | None = None) -> Path:
    """Resolve the destination directory for a project name, safely."""
    validated = validate_project_name(name)
    base = Path.cwd() if cwd is None else cwd
    dest = (base / validated).resolve()
    try:
        dest.relative_to(base.resolve())
    except ValueError as exc:
        raise SklabError(UNSAFE_PATH, f"Unsafe destination: {dest}.") from exc
    return dest


def check_destination(dest: Path, *, force: bool = False) -> None:
    """Raise DESTINATION_EXISTS unless *dest* is usable. Never deletes anything."""
    if not dest.exists():
        return
    if dest.is_file():
        raise SklabError(
            DESTINATION_EXISTS,
            f"Destination already exists: {dest}.",
            remediation="Choose a different project name or remove the file.",
        )
    # Directory exists.
    try:
        is_empty = not any(dest.iterdir())
    except OSError:
        is_empty = False
    if is_empty:
        return
    if not force:
        raise SklabError(
            DESTINATION_EXISTS,
            f"Destination already exists and is not empty: {dest}.",
            remediation="Choose a different project name, or re-run with --force to overlay files.",
        )


class StarterProvider(ABC):
    """Source of starter templates. Never executes remote code."""

    @abstractmethod
    def describe(self) -> str:
        """Human-readable source description (for output, no secrets)."""

    @abstractmethod
    def list_starters(self) -> list[StarterInfo]:
        ...

    @abstractmethod
    def fetch(self, starter: str, dest: Path) -> list[str]:
        """Copy raw starter files into *dest* (created if needed).

        Returns the list of relative paths created. Raises SklabError.
        """


def get_provider(
    source: str | None,
    *,
    branch: str | None = None,
    timeout: int = 30,
    cache_ttl: int = 86400,
) -> StarterProvider:
    """Build the right provider for *source* (local path or GitHub repo)."""
    from sklab.starters.github import GitHubStarterProvider
    from sklab.starters.local import LocalStarterProvider

    if source is None or not str(source).strip():
        source = "sklabstudio/starters"
    text = str(source).strip()
    if Path(text).exists():
        return LocalStarterProvider(Path(text))
    return GitHubStarterProvider(repo=text, branch=branch or "main", timeout=timeout, cache_ttl=cache_ttl)


def require_starter(starter: str) -> str:
    key = starter.strip().lower()
    if key not in STARTERS:
        known = ", ".join(sorted(STARTERS))
        raise SklabError(
            STARTER_NOT_FOUND,
            f"Unknown starter: {starter!r}.",
            remediation=f"Available starters: {known}.",
        )
    return key
