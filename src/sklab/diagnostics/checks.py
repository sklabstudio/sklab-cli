"""Read-only environment/repository diagnostics. Never modifies anything.

Only runs safe inspection commands (``--version``, ``status``, ``rev-parse``).
Never installs packages, never writes files, never starts services.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from sklab.core.subprocess import run_command
from sklab.diagnostics.detector import ProjectInfo, detect_project
from sklab.diagnostics.models import CheckResult, CheckStatus

CHECK_TIMEOUT = 15.0


def run_doctor(root: Path | None = None) -> tuple[ProjectInfo, list[CheckResult]]:
    path = (root or Path.cwd()).resolve()
    info = detect_project(path)
    checks = [
        _check_git(info),
        _check_python(info),
        _check_node(info),
        _check_docker(info),
        _check_compose(info),
        _check_env_file(info),
        _check_tests(info),
        _check_git_status(info),
    ]
    return info, checks


def _check_git(info: ProjectInfo) -> CheckResult:
    result = run_command(["git", "--version"], cwd=info.root, timeout=CHECK_TIMEOUT)
    if result.not_found:
        if info.is_git_repo:
            return CheckResult(
                id="git", name="Git", status=CheckStatus.FAIL,
                message="Directory is a git repository but git is not installed.",
                details={"available": False},
                remediation="Install git: https://git-scm.com/downloads.",
            )
        return CheckResult(
            id="git", name="Git", status=CheckStatus.WARNING,
            message="Git is not installed and this is not a git repository.",
            details={"available": False},
            remediation="Install git if you want version control.",
        )
    version = _first_line(result.stdout) or "available"
    if info.is_git_repo:
        return CheckResult(
            id="git", name="Git", status=CheckStatus.PASS,
            message=f"Git repository detected ({version}).",
            details={"available": True, "version": version, "is_repo": True},
        )
    return CheckResult(
        id="git", name="Git", status=CheckStatus.WARNING,
        message=f"Git is installed ({version}) but this directory is not a git repository.",
        details={"available": True, "version": version, "is_repo": False},
        remediation="Run 'git init' to start tracking this project.",
    )


def _check_python(info: ProjectInfo) -> CheckResult:
    if not info.has_python:
        return CheckResult(
            id="python", name="Python", status=CheckStatus.SKIPPED,
            message="No Python project detected (no pyproject.toml, requirements.txt, or .py files).",
            details={"detected": False, "markers": []},
        )
    result = run_command([sys.executable, "--version"], cwd=info.root, timeout=CHECK_TIMEOUT)
    version = _first_line(result.stdout or result.stderr) or "unknown"
    numbers = re.search(r"(\d+)\.(\d+)", version)
    details: dict[str, object] = {"detected": True, "markers": info.python_files, "version": version}
    if numbers and (int(numbers.group(1)), int(numbers.group(2))) < (3, 9):
        return CheckResult(
            id="python", name="Python", status=CheckStatus.WARNING,
            message=f"Python project detected but interpreter is old ({version}).",
            details=details,
            remediation="Use Python 3.12+ for SKLab starters.",
        )
    return CheckResult(
        id="python", name="Python", status=CheckStatus.PASS,
        message=f"Python detected ({version}).",
        details=details,
    )


def _check_node(info: ProjectInfo) -> CheckResult:
    if not info.has_node:
        return CheckResult(
            id="node", name="Node.js", status=CheckStatus.SKIPPED,
            message="No Node.js project detected (no package.json or TS config).",
            details={"detected": False},
        )
    result = run_command(["node", "--version"], cwd=info.root, timeout=CHECK_TIMEOUT)
    if result.not_found or result.returncode != 0:
        return CheckResult(
            id="node", name="Node.js", status=CheckStatus.FAIL,
            message="Node.js project detected but 'node' is not available.",
            details={"detected": True, "available": False, "markers": info.node_files},
            remediation="Install Node.js 20+: https://nodejs.org.",
        )
    version = _first_line(result.stdout) or "available"
    npm = run_command(["npm", "--version"], cwd=info.root, timeout=CHECK_TIMEOUT)
    return CheckResult(
        id="node", name="Node.js", status=CheckStatus.PASS,
        message=f"Node.js detected ({version}).",
        details={
            "detected": True, "available": True, "version": version,
            "npm": _first_line(npm.stdout) if npm.ok else None,
            "markers": info.node_files,
        },
    )


def _check_docker(info: ProjectInfo) -> CheckResult:
    uses_docker = info.has_dockerfile or info.compose_file is not None
    result = run_command(["docker", "--version"], cwd=info.root, timeout=CHECK_TIMEOUT)
    if not uses_docker:
        if result.ok:
            return CheckResult(
                id="docker", name="Docker", status=CheckStatus.PASS,
                message=f"Docker is available ({_first_line(result.stdout)}); project has no Docker files.",
                details={"available": True, "required": False},
            )
        return CheckResult(
            id="docker", name="Docker", status=CheckStatus.SKIPPED,
            message="No Dockerfile found; Docker not required for this project.",
            details={"available": False, "required": False},
        )
    if not result.ok:
        return CheckResult(
            id="docker", name="Docker", status=CheckStatus.WARNING,
            message="Project uses Docker but the docker CLI is not available.",
            details={"available": False, "required": True},
            remediation="Install Docker Desktop or the Docker Engine: https://docs.docker.com/get-docker/.",
        )
    daemon = run_command(["docker", "info"], cwd=info.root, timeout=CHECK_TIMEOUT)
    if not daemon.ok:
        return CheckResult(
            id="docker", name="Docker", status=CheckStatus.WARNING,
            message="Docker CLI is installed but the daemon does not appear reachable.",
            details={"available": True, "daemon": False, "version": _first_line(result.stdout)},
            remediation="Start Docker Desktop / the docker daemon.",
        )
    return CheckResult(
        id="docker", name="Docker", status=CheckStatus.PASS,
        message=f"Docker is available ({_first_line(result.stdout)}).",
        details={"available": True, "required": True, "version": _first_line(result.stdout)},
    )


def _check_compose(info: ProjectInfo) -> CheckResult:
    if info.compose_file is None:
        return CheckResult(
            id="docker-compose", name="Docker Compose", status=CheckStatus.SKIPPED,
            message="No compose file found (compose.yml / docker-compose.yml).",
            details={"detected": False},
        )
    result = run_command(["docker", "compose", "version"], cwd=info.root, timeout=CHECK_TIMEOUT)
    if result.ok:
        return CheckResult(
            id="docker-compose", name="Docker Compose", status=CheckStatus.PASS,
            message=f"Compose file {info.compose_file.name} with {_first_line(result.stdout)}.",
            details={"detected": True, "file": str(info.compose_file), "version": _first_line(result.stdout)},
        )
    legacy = run_command(["docker-compose", "--version"], cwd=info.root, timeout=CHECK_TIMEOUT)
    if legacy.ok:
        return CheckResult(
            id="docker-compose", name="Docker Compose", status=CheckStatus.PASS,
            message=f"Compose file {info.compose_file.name} with legacy {_first_line(legacy.stdout)}.",
            details={"detected": True, "file": str(info.compose_file)},
        )
    return CheckResult(
        id="docker-compose", name="Docker Compose", status=CheckStatus.WARNING,
        message=f"Compose file {info.compose_file.name} found but neither 'docker compose' nor 'docker-compose' works.",
        details={"detected": True, "file": str(info.compose_file)},
        remediation="Install a recent Docker version with Compose v2.",
    )


def _check_env_file(info: ProjectInfo) -> CheckResult:
    if info.has_env_example and info.has_env:
        return CheckResult(
            id="env-file", name="Environment file", status=CheckStatus.PASS,
            message=".env exists alongside .env.example.",
            details={"example": True, "env": True},
        )
    if info.has_env_example and not info.has_env:
        return CheckResult(
            id="env-file", name="Environment file", status=CheckStatus.WARNING,
            message=".env.example exists but .env is missing.",
            details={"example": True, "env": False},
            remediation=(
                "Copy the template: 'cp .env.example .env' (Windows: 'copy .env.example .env'), "
                "then fill in values."
            ),
        )
    if info.has_env and not info.has_env_example:
        return CheckResult(
            id="env-file", name="Environment file", status=CheckStatus.WARNING,
            message=".env exists but no .env.example documents required variables.",
            details={"example": False, "env": True},
            remediation="Add a .env.example so new contributors know which variables to set.",
        )
    return CheckResult(
        id="env-file", name="Environment file", status=CheckStatus.SKIPPED,
        message="No environment template (.env.example) detected.",
        details={"example": False, "env": False},
    )


def _check_tests(info: ProjectInfo) -> CheckResult:
    if not info.has_tests:
        return CheckResult(
            id="tests", name="Tests", status=CheckStatus.SKIPPED,
            message="No test setup detected (no tests/ dir, pytest config, or npm test script).",
            details={"detected": False},
        )
    return CheckResult(
        id="tests", name="Tests", status=CheckStatus.PASS,
        message=f"Test setup detected ({', '.join(info.test_kinds)}).",
        details={"detected": True, "kinds": info.test_kinds},
    )


def _check_git_status(info: ProjectInfo) -> CheckResult:
    if not info.is_git_repo:
        return CheckResult(
            id="git-status", name="Git status", status=CheckStatus.SKIPPED,
            message="Not a git repository.",
            details={"is_repo": False},
        )
    result = run_command(["git", "status", "--porcelain"], cwd=info.root, timeout=CHECK_TIMEOUT)
    if result.not_found:
        return CheckResult(
            id="git-status", name="Git status", status=CheckStatus.UNKNOWN,
            message="Git is not installed; cannot inspect working tree.",
            details={"is_repo": True},
        )
    if result.returncode != 0:
        return CheckResult(
            id="git-status", name="Git status", status=CheckStatus.UNKNOWN,
            message="Could not read git status.",
            details={"is_repo": True, "stderr": result.stderr[:500]},
        )
    if result.stdout.strip():
        dirty_lines = len([line for line in result.stdout.splitlines() if line.strip()])
        return CheckResult(
            id="git-status", name="Git status", status=CheckStatus.WARNING,
            message=f"Working tree has {dirty_lines} changed/untracked file(s).",
            details={"is_repo": True, "clean": False, "changed_files": dirty_lines},
            remediation="Commit or stash changes before releasing.",
        )
    return CheckResult(
        id="git-status", name="Git status", status=CheckStatus.PASS,
        message="Working tree is clean.",
        details={"is_repo": True, "clean": True},
    )


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""
