"""Safe subprocess execution: argument arrays only, timeouts, captured output."""

from __future__ import annotations

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
    try:
        completed = subprocess.run(
            argv,
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
