"""Validation, slugging, destination safety."""

from __future__ import annotations

import pytest

from sklab.core.errors import SklabError
from sklab.starters.provider import (
    check_destination,
    resolve_destination,
    slugify,
    validate_project_name,
)


@pytest.mark.parametrize("name", ["my-app", "invoice-app", "a", "App_1", "my.app-2_x", "x" * 214])
def test_valid_project_names(name: str) -> None:
    assert validate_project_name(name) == name.strip()


@pytest.mark.parametrize(
    "name",
    ["", "  ", "../evil", "a/b", "a\\b", ".", "..", "-bad", ".bad", "_bad", "has space", "semi;colon", "con", "NUL.txt"],
)
def test_invalid_project_names(name: str) -> None:
    with pytest.raises(SklabError):
        validate_project_name(name)


def test_slugify() -> None:
    assert slugify("Invoice App") == "invoice-app"
    assert slugify("My_API.Service!") == "my-api-service"
    assert slugify("---") == "app"


def test_resolve_destination_inside_cwd(tmp_path) -> None:
    dest = resolve_destination("demo", cwd=tmp_path)
    assert dest.parent == tmp_path.resolve()
    assert dest.name == "demo"


def test_check_destination_missing_ok(tmp_path) -> None:
    check_destination(tmp_path / "fresh")  # must not raise


def test_check_destination_file_collision(tmp_path) -> None:
    target = tmp_path / "taken"
    target.write_text("x")
    with pytest.raises(SklabError) as exc_info:
        check_destination(target)
    assert exc_info.value.code == "DESTINATION_EXISTS"


def test_check_destination_nonempty_dir(tmp_path) -> None:
    target = tmp_path / "proj"
    target.mkdir()
    (target / "file.txt").write_text("user data")
    with pytest.raises(SklabError) as exc_info:
        check_destination(target)
    assert exc_info.value.code == "DESTINATION_EXISTS"
    # Existing content must be untouched.
    assert (target / "file.txt").read_text() == "user data"


def test_check_destination_empty_dir_ok(tmp_path) -> None:
    target = tmp_path / "proj"
    target.mkdir()
    check_destination(target)  # must not raise


def test_check_destination_force_allows_overlay(tmp_path) -> None:
    target = tmp_path / "proj"
    target.mkdir()
    (target / "file.txt").write_text("user data")
    check_destination(target, force=True)  # must not raise
