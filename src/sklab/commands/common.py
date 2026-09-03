"""Shared helpers for command modules: uniform error handling."""

from __future__ import annotations

import traceback
from typing import NoReturn

import typer

from sklab.core import output
from sklab.core.errors import INTERNAL_ERROR, SklabError


def fail(exc: SklabError, *, json_mode: bool = False) -> NoReturn:
    if json_mode:
        output.print_json({"error": exc.to_dict()})
    else:
        output.error(exc.format())
    raise typer.Exit(code=exc.exit_code)


def handle_unexpected(exc: Exception, *, json_mode: bool = False, exit_code: int = 3) -> NoReturn:
    if output.is_verbose():
        traceback.print_exc()
    if json_mode:
        output.print_json(
            {
                "error": {
                    "code": INTERNAL_ERROR,
                    "message": f"Internal error: {exc}",
                    "remediation": "Re-run with --verbose and report the issue.",
                }
            }
        )
    else:
        output.error(f"Error [{INTERNAL_ERROR}]: {exc}\n  Fix: Re-run with --verbose for details.")
    raise typer.Exit(code=exit_code)
