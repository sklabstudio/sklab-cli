"""Terminal output helpers built on Rich with safe non-TTY / CI degradation."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from rich.console import Console

_state: dict[str, bool] = {"verbose": False, "quiet": False, "no_color": False}


def configure_output(*, verbose: bool = False, quiet: bool = False, no_color: bool = False) -> None:
    _state["verbose"] = verbose
    _state["quiet"] = quiet
    _state["no_color"] = no_color


def is_verbose() -> bool:
    return _state["verbose"]


def is_quiet() -> bool:
    return _state["quiet"]


def _no_color_requested(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    if _state["no_color"]:
        return True
    if os.environ.get("NO_COLOR"):
        return True
    return not sys.stdout.isatty()


def _ascii_only() -> bool:
    """True when stdout cannot render symbols like ✓/✗ (e.g. Windows cp1252)."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✓✗!".encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return True
    return False


def get_console(*, no_color: bool | None = None, stderr: bool = False) -> Console:
    return Console(no_color=_no_color_requested(no_color), stderr=stderr)


def info(message: str) -> None:
    if _state["quiet"]:
        return
    get_console().print(message)


def success(message: str) -> None:
    if _state["quiet"]:
        return
    mark = "+" if _ascii_only() else "✓"
    if _ascii_only() or get_console().no_color:
        get_console().print(f"{mark} {message}")
    else:
        get_console().print(f"[green]{mark}[/green] {message}")


def warning(message: str) -> None:
    get_console(stderr=True).print(f"! {message}" if _ascii_only() else f"[yellow]![/yellow] {message}")


def error(message: str) -> None:
    get_console(stderr=True).print(f"x {message}" if _ascii_only() else f"[red]✗[/red] {message}")


def print_json(data: Any) -> None:
    # Plain print: no Rich wrapping, always valid JSON for automation.
    print(json.dumps(data, indent=2))


def print_text(text: str) -> None:
    """Print arbitrary text (e.g. Markdown resources) without ever crashing.

    Raw markdown goes to stdout so it can be piped. On consoles that cannot
    represent some characters, fall back to ``\\uXXXX`` escapes for those
    characters instead of raising UnicodeEncodeError.
    """
    ending = "" if text.endswith("\n") else "\n"
    try:
        print(text, end=ending)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = text.encode(encoding, errors="backslashreplace").decode(encoding)
        print(safe, end=ending)


def header(title: str) -> None:
    if _state["quiet"]:
        return
    get_console().print(f"[bold]{title}[/bold]\n")


STATUS_STYLES: dict[str, str] = {
    "PASS": "green",
    "READY": "green",
    "WARNING": "yellow",
    "DEGRADED": "yellow",
    "READY_WITH_WARNINGS": "yellow",
    "FAIL": "red",
    "FAILED": "red",
    "NOT_READY": "red",
    "SKIPPED": "dim",
    "NOT_INSTALLED": "dim",
    "UNAVAILABLE": "dim",
    "UNKNOWN": "dim",
}


_ASCII_SYMBOLS = {
    "PASS": "+", "READY": "+", "WARNING": "!", "DEGRADED": "!", "READY_WITH_WARNINGS": "!",
    "FAIL": "x", "FAILED": "x", "NOT_READY": "x",
}
_UNICODE_SYMBOLS = {
    "PASS": "✓", "READY": "✓", "WARNING": "!", "DEGRADED": "!", "READY_WITH_WARNINGS": "!",
    "FAIL": "✗", "FAILED": "✗", "NOT_READY": "✗",
}


def status_symbol(status: str) -> str:
    table = _ASCII_SYMBOLS if _ascii_only() else _UNICODE_SYMBOLS
    return table.get(status, "-")


def format_status(status: str, *, no_color: bool | None = None) -> str:
    console = get_console(no_color=no_color)
    style = STATUS_STYLES.get(status)
    text = f"{status_symbol(status)} {status}"
    if style and not console.no_color:
        return f"[{style}]{text}[/{style}]"
    return text


def styled_status(status: str) -> str:
    """Status cell for Rich tables; degrades to plain text with --no-color/NO_COLOR."""
    return format_status(status)
