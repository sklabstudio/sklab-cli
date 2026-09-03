"""Ship-check planning: decide which commands to run from standard project config.

Only well-understood commands discovered from real config files are planned.
Never invents npm scripts; never plans destructive commands.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sklab.core.subprocess import PlannedStep
from sklab.diagnostics.detector import ProjectInfo


def build_plan(info: ProjectInfo) -> list[PlannedStep]:
    steps: list[PlannedStep] = []
    steps.append(
        PlannedStep(
            id="git-status",
            name="Git status",
            argv=["git", "status", "--porcelain"],
            description="Working tree must be clean.",
        )
    )
    if info.has_python and info.has_tests and "pytest" in info.test_kinds:
        steps.append(
            PlannedStep(
                id="python-tests",
                name="Python tests",
                argv=[sys.executable, "-m", "pytest", "-q"],
                description="Run the Python test suite.",
            )
        )
    scripts = info.node_scripts
    if info.has_node and "test" in scripts:
        steps.append(
            PlannedStep(
                id="node-test", name="Node tests", argv=["npm", "test", "--silent"],
                description="Run 'npm test' (script exists in package.json).",
            )
        )
    if info.has_node and "lint" in scripts:
        steps.append(
            PlannedStep(
                id="node-lint", name="Node lint", argv=["npm", "run", "lint", "--silent"],
                description="Run 'npm run lint' (script exists in package.json).",
            )
        )
    if info.has_node and "build" in scripts:
        steps.append(
            PlannedStep(
                id="node-build", name="Node build", argv=["npm", "run", "build", "--silent"],
                description="Run 'npm run build' (script exists in package.json).",
            )
        )
    if info.compose_file is not None:
        steps.append(
            PlannedStep(
                id="compose-config",
                name="Compose config",
                argv=["docker", "compose", "config", "--quiet"],
                description=f"Validate {info.compose_file.name}.",
            )
        )
    steps.append(
        PlannedStep(
            id="env-docs",
            name="Required env docs",
            kind="inspection",
            description="Check .env.example documents required variables.",
        )
    )
    steps.append(PlannedStep(id="readme", name="README", kind="inspection", description="Check a README exists."))
    return steps


def describe_plan(steps: list[PlannedStep]) -> list[str]:
    lines: list[str] = []
    for i, step in enumerate(steps, start=1):
        if step.kind == "inspection":
            lines.append(f"{i}. [inspect] {step.name}: {step.description}")
        else:
            lines.append(f"{i}. {' '.join(step.argv)}")
    return lines


def plan_for_path(root: Path) -> tuple[ProjectInfo, list[PlannedStep]]:
    from sklab.diagnostics.detector import detect_project

    info = detect_project(root.resolve())
    return info, build_plan(info)
