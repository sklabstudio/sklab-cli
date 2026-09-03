"""Deliberately simple template processing: plain placeholder substitution only.

Supported placeholders: {{PROJECT_NAME}}, {{PROJECT_SLUG}}.
Never executes code, never runs template-provided commands.
"""

from __future__ import annotations

import re
from pathlib import Path

from sklab.starters.provider import slugify

PLACEHOLDER_RE = re.compile(r"\{\{\s*(PROJECT_NAME|PROJECT_SLUG)\s*\}\}")

MAX_TEXT_BYTES = 1024 * 1024

SKIP_DIR_PARTS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "dist", "build",
}


def render_text(text: str, project_name: str) -> str:
    mapping = {"PROJECT_NAME": project_name, "PROJECT_SLUG": slugify(project_name)}

    def _replace(match: re.Match[str]) -> str:
        return mapping[match.group(1)]

    return PLACEHOLDER_RE.sub(_replace, text)


def process_templates(project_dir: Path, project_name: str) -> int:
    """Substitute placeholders in text files under *project_dir*. Returns files changed."""
    changed = 0
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(project_dir).parts
        if any(part in SKIP_DIR_PARTS for part in rel_parts):
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
        except OSError:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: leave untouched
        if "{{" not in text:
            continue
        rendered = render_text(text, project_name)
        if rendered != text:
            path.write_text(rendered, encoding="utf-8")
            changed += 1
    return changed
