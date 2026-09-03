"""Safe subprocess execution: argument arrays only, timeouts, captured output."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    not_found: bool = False

    @property
    def ok(self) -> bool:
        return not self.timed_out and not self.not_found and self.returncode == 0


MAX_OUTPUT_CHARS = 8000


def run_command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 60.0,
) -> CommandResult:
    """Run *argv* without a shell, capturing output. Never raises on missing binary."""
    if not argv or not all(isinstance(a, str) for a in argv):
        raise ValueError("argv must be a non-empty list of strings")
    effective = _apply_windows_shim(argv)
    try:
        completed = subprocess.run(
            effective,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(argv=list(argv), returncode=127, stderr="command not found", not_found=True)
    except subprocess.TimeoutExpired as exc:
        stdout = _truncate(exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        stderr = _truncate(exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
        return CommandResult(argv=list(argv), returncode=124, stdout=stdout, stderr=stderr, timed_out=True)
    except OSError as exc:
        return CommandResult(argv=list(argv), returncode=127, stderr=str(exc), not_found=True)
    return CommandResult(
        argv=list(argv),
        returncode=completed.returncode,
        stdout=_truncate(completed.stdout or ""),
        stderr=_truncate(completed.stderr or ""),
    )


def _apply_windows_shim(argv: list[str], *, os_name: str = os.name) -> list[str] | str:
    """Route Windows .cmd/.bat shims (e.g. npm.cmd) through cmd.exe.

    ``CreateProcess`` cannot launch batch scripts directly, so without this an
    installed ``npm`` is misreported as missing. The shim returns a single
    command-line string in the canonical ``cmd /s /c ""exe" args"`` form
    (passing a list would make list2cmdline re-escape the quotes and break
    paths with spaces). Still no ``shell=True``; arguments are quoted with
    list2cmdline so each stays a single cmd token, and only fixed,
    well-understood argv are ever executed (never user input).
    """
    if os_name != "nt" or not argv:
        return argv
    try:
        resolved = shutil.which(argv[0])
    except OSError:
        return argv
    if resolved and os.path.splitext(resolved)[1].lower() in (".cmd", ".bat"):
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        inner = subprocess.list2cmdline([resolved, *argv[1:]])
        return f'{comspec} /d /s /c "{inner}"'
    return argv


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"
    return text


@dataclass
class PlannedStep:
    id: str
    name: str
    argv: list[str] = field(default_factory=list)
    description: str = ""
    kind: str = "command"  # "command" | "inspection"
