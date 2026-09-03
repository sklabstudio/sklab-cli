"""Repository/technology detection from well-known files (no execution)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectInfo:
    root: Path
    is_git_repo: bool = False
    has_python: bool = False
    python_files: list[str] = field(default_factory=list)
    has_node: bool = False
    node_files: list[str] = field(default_factory=list)
    node_scripts: dict[str, str] = field(default_factory=dict)
    has_dockerfile: bool = False
    compose_file: Path | None = None
    has_env_example: bool = False
    has_env: bool = False
    has_readme: bool = False
    has_tests: bool = False
    test_kinds: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "is_git_repo": self.is_git_repo,
            "has_python": self.has_python,
            "has_node": self.has_node,
            "has_dockerfile": self.has_dockerfile,
            "compose_file": str(self.compose_file) if self.compose_file else None,
            "has_env_example": self.has_env_example,
            "has_env": self.has_env,
            "has_readme": self.has_readme,
            "has_tests": self.has_tests,
            "technologies": self.technologies,
        }


def detect_project(root: Path) -> ProjectInfo:
    root = root.resolve()
    info = ProjectInfo(root=root)
    info.is_git_repo = (root / ".git").exists()

    python_markers = ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile", "poetry.lock"]
    for marker in python_markers:
        if (root / marker).exists():
            info.has_python = True
            info.python_files.append(marker)
    if (root / "app").is_dir() or (root / "src").is_dir():
        # Weak signal only in combination; check for .py files one level deep.
        for sub in ("app", "src", "tests"):
            if any((root / sub).glob("*.py")):
                info.has_python = True
    if list(root.glob("*.py")):
        info.has_python = True

    package_json = root / "package.json"
    if package_json.exists():
        info.has_node = True
        info.node_files.append("package.json")
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if isinstance(scripts, dict):
                info.node_scripts = {k: str(v) for k, v in scripts.items()}
        except (OSError, ValueError):
            info.node_scripts = {}
    for marker in ("next.config.js", "next.config.mjs", "next.config.ts", "tsconfig.json", "vite.config.ts"):
        if (root / marker).exists() or list(root.glob(marker)):
            info.has_node = True
            info.node_files.append(marker)

    if (root / "Dockerfile").exists() or (root / "docker" / "Dockerfile").exists():
        info.has_dockerfile = True
    for candidate in ("compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"):
        if (root / candidate).exists():
            info.compose_file = root / candidate
            break

    info.has_env_example = (root / ".env.example").exists()
    info.has_env = (root / ".env").exists()
    info.has_readme = any((root / name).exists() for name in ("README.md", "README.rst", "README.txt", "README"))

    test_kinds: list[str] = []
    if (
        (root / "pytest.ini").exists()
        or (root / "tests").is_dir()
        or (root / "test").is_dir()
        or "pytest.ini" in info.python_files
        or "pyproject.toml" in info.python_files
    ):
        if info.has_python and ((_has_pytest_config(root)) or (root / "tests").is_dir() or (root / "test").is_dir()):
            test_kinds.append("pytest")
    if info.has_node and "test" in info.node_scripts:
        test_kinds.append("npm test")
    if test_kinds:
        info.has_tests = True
        info.test_kinds = test_kinds

    techs: list[str] = []
    if info.has_python:
        techs.append("python")
    if info.has_node:
        techs.append("node")
    if info.has_dockerfile or info.compose_file is not None:
        techs.append("docker")
    info.technologies = techs
    return info


def _has_pytest_config(root: Path) -> bool:
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return False
        return "[tool.pytest" in text or "[pytest" in text or "pytest" in text and "testpaths" in text
    return False
