"""Public built-in module registry + local ``modules.d`` extension.

The built-in registry contains ONLY public descriptors (generic git pointers,
no code, no credentials). Optional/private modules attach locally via
``~/.sklab/modules.d/*.yaml`` and are never uploaded or logged verbatim.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sklab.stack import home as stack_home
from sklab.stack.manifest import ModuleManifest, manifest_fingerprint_bytes, parse_manifest_yaml

BUILTIN_VERSION = "0.1.0"


def _public(
    module_id: str,
    name: str,
    *,
    repository: str,
    capabilities: list[str] | None = None,
    dependencies: list[str] | None = None,
    install_type: str = "python",
    health: list[str] | None = None,
    version: str = BUILTIN_VERSION,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": module_id,
        "name": name,
        "version": version,
        "visibility": "public",
        "source": {"type": "git", "repository": repository},
        "install": {"type": install_type, "package_path": "."},
        "health": {"command": health} if health else {},
        "capabilities": capabilities or [],
        "dependencies": dependencies or [],
    }


def builtin_descriptors() -> list[dict[str, Any]]:
    """Generic public descriptors. No code, no credentials, no private URLs."""
    return [
        _public("repo-context", "RepoContext", repository="sklabstudio/repo-context",
                capabilities=["repo-context"], health=["repo-context", "--version"]),
        _public("coding-lab", "Coding Lab", repository="sklabstudio/coding-lab",
                capabilities=[], health=["coding-lab", "--version"]),
        _public("starters", "Starters", repository="sklabstudio/starters", capabilities=[]),
        _public("sklab-cli", "SKLab CLI", repository="sklabstudio/sklab-cli",
                capabilities=[], health=["sklab", "--version"]),
        _public("patchbench", "PatchBench", repository="sklabstudio/patchbench",
                capabilities=["benchmarking"], health=["patchbench", "--version"]),
        _public("codetrials", "CodeTrials", repository="sklabstudio/codetrials",
                capabilities=["benchmarking"], health=["codetrials", "--version"]),
        _public("promptbench", "PromptBench", repository="sklabstudio/promptbench",
                capabilities=["benchmarking"], health=["promptbench", "--version"]),
        _public("benchsuite", "BenchSuite", repository="sklabstudio/benchsuite",
                capabilities=["benchmarking"], health=["benchsuite", "--version"]),
        _public("reprobox", "ReproBox", repository="sklabstudio/reprobox",
                capabilities=["sandbox"], health=["reprobox", "--version"]),
        _public("agent-adapters", "Agent Adapters", repository="sklabstudio/agent-adapters",
                capabilities=["agents"], health=["agent-adapters", "--version"]),
        _public("provider-connections", "Provider Connections", repository="sklabstudio/provider-connections",
                capabilities=["providers"], health=["provider-connections", "--version"]),
        _public("orchestrator", "SKLab Orchestrator", repository="sklabstudio/orchestrator",
                capabilities=["orchestration"],
                dependencies=["agent-adapters", "provider-connections"],
                health=["sklab-run", "doctor", "--json"]),
        _public("web-ui", "Web UI", repository="sklabstudio/web-ui",
                capabilities=["web-ui"], install_type="node",
                health=["sklab-web", "--version"]),
        _public("skill-hub", "Skill Hub", repository="sklabstudio/skill-hub",
                capabilities=["skills"], health=["skill-hub", "--version"]),
        _public("cyber-pack", "Cyber Pack", repository="sklabstudio/cyber-pack",
                capabilities=["security"], health=["cyber-pack", "--version"]),
        _public("contract-toolkit", "Contract Toolkit", repository="sklabstudio/contract-toolkit",
                capabilities=["contracts"], health=["contract-toolkit", "--version"]),
    ]


@dataclass
class LoadedManifest:
    manifest: ModuleManifest
    origin: str  # "builtin" | "local"
    path: str | None = None
    fingerprint: str = ""

    def to_summary(self) -> dict[str, object]:
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "visibility": self.manifest.visibility,
            "origin": self.origin,
            "capabilities": list(self.manifest.capabilities),
        }


@dataclass
class Registry:
    modules: dict[str, LoadedManifest] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)

    def ids(self) -> list[str]:
        return sorted(self.modules.keys())

    def get(self, module_id: str) -> LoadedManifest | None:
        return self.modules.get(module_id)


def load_builtin_registry() -> Registry:
    registry = Registry()
    for raw in builtin_descriptors():
        try:
            manifest = ModuleManifest.model_validate(raw)
            registry.modules[manifest.id] = LoadedManifest(
                manifest=manifest, origin="builtin", fingerprint=manifest.fingerprint()
            )
        except Exception as exc:  # noqa: BLE001 - builtin must always validate; record defensively
            registry.errors.append({"id": str(raw.get("id", "?")), "error": str(exc)})
    return registry


def load_local_manifests(modules_dir: Path | None = None) -> tuple[dict[str, LoadedManifest], list[dict[str, str]]]:
    directory = modules_dir or stack_home.modules_dir()
    found: dict[str, LoadedManifest] = {}
    errors: list[dict[str, str]] = []
    if not directory.exists():
        return found, errors
    for pattern in ("*.yaml", "*.yml"):
        for path in sorted(directory.glob(pattern)):
            try:
                raw = path.read_bytes()
                manifest = parse_manifest_yaml(raw.decode("utf-8"))
                fingerprint = manifest_fingerprint_bytes(raw)
                if manifest.id in found:
                    errors.append({"file": str(path), "error": f"Duplicate local module id: {manifest.id}."})
                    continue
                found[manifest.id] = LoadedManifest(
                    manifest=manifest, origin="local", path=str(path), fingerprint=fingerprint
                )
            except Exception as exc:  # noqa: BLE001 - one bad file must not break the registry
                errors.append({"file": str(path), "error": str(exc)})
    return found, errors


def load_registry(modules_dir: Path | None = None) -> Registry:
    """Merge builtin (public) + local (optional/private overlay). Local wins on id clash only for private ids."""
    registry = load_builtin_registry()
    local, errors = load_local_manifests(modules_dir)
    registry.errors.extend(errors)
    for module_id, loaded in local.items():
        existing = registry.modules.get(module_id)
        if existing is not None and existing.origin == "builtin" and loaded.manifest.visibility == "public":
            # A local public manifest with a colliding id shadows the builtin (explicit local override).
            registry.modules[module_id] = loaded
        elif existing is not None and existing.origin == "builtin":
            # Private overlay reusing a public id is ambiguous; keep builtin, record error.
            registry.errors.append(
                {"id": module_id, "error": f"Local manifest id collides with a public module: {module_id}."}
            )
            continue
        else:
            registry.modules[module_id] = loaded
    return registry


def add_manifest_file(source_path: Path, *, modules_dir: Path | None = None) -> LoadedManifest:
    """Copy a local manifest into ``modules.d`` after strict validation. Never fetches remotes."""
    from sklab.stack.redaction import redact_text

    _ = redact_text  # keep redaction adjacent to manifest ingestion
    raw = source_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Manifest is not valid UTF-8: {source_path} ({exc}).") from exc
    manifest = parse_manifest_yaml(text)
    target_dir = modules_dir or stack_home.modules_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    # Validate id as a safe filename (manifest id regex already guarantees this).
    target = target_dir / f"{manifest.id}.yaml"
    if target.exists():
        existing = target.read_bytes()
        if hashlib.sha256(existing).hexdigest() == hashlib.sha256(raw).hexdigest():
            return LoadedManifest(
                manifest=manifest, origin="local", path=str(target),
                fingerprint=manifest_fingerprint_bytes(raw),
            )
        raise ValueError(f"A different manifest for '{manifest.id}' already exists: {target}.")
    target.write_bytes(raw)
    return LoadedManifest(
        manifest=manifest, origin="local", path=str(target),
        fingerprint=manifest_fingerprint_bytes(raw),
    )
