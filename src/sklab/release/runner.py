"""Ship-check execution: run the plan with timeouts, capture output, compute a verdict."""

from __future__ import annotations

import time
from pathlib import Path

from sklab.core.subprocess import CommandResult, PlannedStep, run_command
from sklab.diagnostics.detector import ProjectInfo
from sklab.diagnostics.models import CheckResult, CheckStatus
from sklab.release.models import ShipReport, Verdict
from sklab.release.planner import build_plan

DEFAULT_COMMAND_TIMEOUT = 600.0


def run_shipcheck(root: Path, *, timeout_per_command: float = DEFAULT_COMMAND_TIMEOUT) -> ShipReport:
    from sklab.diagnostics.detector import detect_project

    started = time.perf_counter()
    info = detect_project(root.resolve())
    steps = build_plan(info)
    checks: list[CheckResult] = []
    for step in steps:
        checks.append(_execute_step(step, info, timeout_per_command))
    verdict = _verdict_for(checks)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return ShipReport(verdict=verdict, checks=checks, duration_ms=duration_ms, root=str(info.root))


def _verdict_for(checks: list[CheckResult]) -> Verdict:
    if any(c.status == CheckStatus.FAIL for c in checks):
        return Verdict.NOT_READY
    if any(c.status in (CheckStatus.WARNING, CheckStatus.UNKNOWN) for c in checks):
        return Verdict.READY_WITH_WARNINGS
    return Verdict.READY


def _execute_step(step: PlannedStep, info: ProjectInfo, timeout: float) -> CheckResult:
    if step.kind == "inspection":
        return _inspect(step, info)
    result = run_command(step.argv, cwd=info.root, timeout=timeout)
    label = step.name
    if result.timed_out:
        return CheckResult(
            id=step.id, name=label, status=CheckStatus.FAIL,
            message=f"{label} timed out after {timeout:g}s.",
            details={"argv": step.argv, "timed_out": True},
            remediation="Investigate why the command hangs, then re-run shipcheck.",
        )
    if result.not_found:
        binary = step.argv[0] if step.argv else "command"
        return CheckResult(
            id=step.id, name=label, status=CheckStatus.FAIL,
            message=f"{label} could not run: '{binary}' is not installed.",
            details={"argv": step.argv, "not_found": True},
            remediation=f"Install '{binary}' or remove the corresponding project setup.",
        )
    if step.id == "git-status":
        return _git_status_result(step, result)
    if result.returncode == 0:
        return CheckResult(
            id=step.id, name=label, status=CheckStatus.PASS,
            message=f"{label} passed.",
            details={"argv": step.argv, "returncode": 0},
        )
    tail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip().splitlines()
    excerpt = "\n".join(tail[-15:])[:2000]
    return CheckResult(
        id=step.id, name=label, status=CheckStatus.FAIL,
        message=f"{label} failed (exit {result.returncode}).",
        details={"argv": step.argv, "returncode": result.returncode, "output_tail": excerpt},
        remediation=f"Run '{' '.join(step.argv)}' locally and fix the failures.",
    )


def _git_status_result(step: PlannedStep, result: CommandResult) -> CheckResult:
    if result.returncode != 0 and not result.not_found:
        if "not a git repository" in (result.stderr or "").lower():
            return CheckResult(
                id=step.id, name=step.name, status=CheckStatus.FAIL,
                message="Not a git repository.",
                details={"argv": step.argv},
                remediation="Run 'git init' and commit your work before releasing.",
            )
        return CheckResult(
            id=step.id, name=step.name, status=CheckStatus.UNKNOWN,
            message="Could not read git status.",
            details={"argv": step.argv, "stderr": result.stderr[:1000]},
        )
    if result.stdout.strip():
        n = len([ln for ln in result.stdout.splitlines() if ln.strip()])
        return CheckResult(
            id=step.id, name=step.name, status=CheckStatus.FAIL,
            message=f"Working tree is dirty ({n} changed/untracked file(s)).",
            details={"argv": step.argv, "clean": False, "changed_files": n},
            remediation="Commit or stash changes before releasing.",
        )
    return CheckResult(
        id=step.id, name=step.name, status=CheckStatus.PASS,
        message="Working tree is clean.",
        details={"argv": step.argv, "clean": True},
    )


def _inspect(step: PlannedStep, info: ProjectInfo) -> CheckResult:
    if step.id == "env-docs":
        if info.has_env_example:
            return CheckResult(
                id=step.id, name=step.name, status=CheckStatus.PASS,
                message=".env.example documents required environment variables.",
                details={"example": True},
            )
        if info.has_env:
            return CheckResult(
                id=step.id, name=step.name, status=CheckStatus.WARNING,
                message=".env exists but no .env.example documents required variables.",
                details={"example": False, "env": True},
                remediation="Add a .env.example listing every required variable.",
            )
        return CheckResult(
            id=step.id, name=step.name, status=CheckStatus.SKIPPED,
            message="No environment files detected; nothing to document.",
            details={"example": False, "env": False},
        )
    if step.id == "readme":
        if info.has_readme:
            return CheckResult(
                id=step.id, name=step.name, status=CheckStatus.PASS,
                message="README found.",
                details={},
            )
        return CheckResult(
            id=step.id, name=step.name, status=CheckStatus.WARNING,
            message="No README found.",
            details={},
            remediation="Add a README.md describing setup and deployment.",
        )
    return CheckResult(id=step.id, name=step.name, status=CheckStatus.UNKNOWN, message="Unknown inspection.")
