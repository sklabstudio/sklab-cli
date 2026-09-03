"""Coding Lab resource lookup (offline, local fixtures)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sklab.core.errors import SklabError
from sklab.resources.coding_lab import CodingLab


def test_list_prompts(coding_lab_source: Path) -> None:
    lab = CodingLab(source=str(coding_lab_source))
    names = [r.name for r in lab.list_prompts()]
    assert "audit-repository" in names
    assert "production-readiness" in names


def test_list_workflows(coding_lab_source: Path) -> None:
    lab = CodingLab(source=str(coding_lab_source))
    names = [r.name for r in lab.list_workflows()]
    assert "repo-rescue" in names
    assert "production-hardening" in names


def test_get_prompt_content(coding_lab_source: Path) -> None:
    lab = CodingLab(source=str(coding_lab_source))
    text = lab.read_resource("prompts", "audit-repository")
    assert "Audit Repository" in text


def test_lookup_is_case_insensitive(coding_lab_source: Path) -> None:
    lab = CodingLab(source=str(coding_lab_source))
    assert lab.get_prompt("Audit-Repository").stem.lower() == "audit-repository"


def test_missing_resource_error(coding_lab_source: Path) -> None:
    lab = CodingLab(source=str(coding_lab_source))
    with pytest.raises(SklabError) as exc_info:
        lab.read_resource("prompts", "does-not-exist")
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"


def test_path_traversal_rejected(coding_lab_source: Path) -> None:
    lab = CodingLab(source=str(coding_lab_source))
    with pytest.raises(SklabError) as exc_info:
        lab.read_resource("prompts", "../workflows/repo-rescue")
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"
