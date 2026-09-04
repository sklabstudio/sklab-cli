"""Stack operations: setup planning/execution, status, doctor, update, clean."""

from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sklab.core.subprocess import run_command
from sklab.stack import adapters
from sklab.stack import home as stack_home
from sklab.stack.adapters import AdapterResult
from sklab.stack.manifest import ModuleManifest
from sklab.stack.redaction import redact_text
from sklab.stack.registry import LoadedManifest, Registry
from sklab.stack.resolver import ResolverError, resolve
from sklab.stack.state import load_state, record_module, save_state

HEALTH_TIMEOUT = 15.0
HEALTH_STATUSES = ("READY", "DEGRADED", "FAILED", "NOT_INSTALLED", "UNAVAILABLE", "UNKNOWN")


@dataclass
class ModuleStatus:
    id: str
    name: str
    version: str
    status: str
    detail: str = ""
    origin: str = ""
    visibility: str = ""


@dataclass
class SetupPlanStep:
    id: str
    action: str  # install | skip | unavailable
    reason: str
    argv_preview: list[list[str]] = field(default_factory=list)


@dataclass
class SetupResult:
    order: list[str]
    results: dict[str, AdapterResult]
    health: dict[str, ModuleStatus]
    summary: dict[str, int]


def check_health(manifest: ModuleManifest) -> ModuleStatus:
    base = ModuleStatus(
        id=manifest.id, name=manifest.name, version=manifest.version,
        status="UNKNOWN", origin="", visibility=manifest.visibility,
    )
    command = manifest.health.command if manifest.health and manifest.health.command else None
    if command:
        timeout = manifest.health.timeout if manifest.health and manifest.health.timeout else HEALTH_TIMEOUT
        result = run_command(list(command), timeout=float(timeout))
        if result.not_found:
            return ModuleStatus(base.id, base.name, base.version, "NOT_INSTALLED",
                                f"Health command not found: {command[0]}.", base.origin, base.visibility)
        if result.timed_out:
            return ModuleStatus(base.id, base.name, base.version, "UNKNOWN",
                                "Health check timed out.", base.origin, base.visibility)
        if result.returncode == 0:
            return ModuleStatus(base.id, base.name, base.version, "READY",
                                "Health check passed.", base.origin, base.visibility)
        if result.returncode == 1:
            return ModuleStatus(base.id, base.name, base.version, "DEGRADED",
                                f"Health check reported degraded (exit 1). {result.stderr[:200]}".strip(),
                                base.origin, base.visibility)
        return ModuleStatus(base.id, base.name, base.version, "FAILED",
                            f"Health check failed (exit {result.returncode}).",
                            base.origin, base.visibility)
    exe = manifest.cli or manifest.executable
    if exe:
        if shutil.which(exe):
            return ModuleStatus(base.id, base.name, base.version, "READY",
                                f"Executable '{exe}' found.", base.origin, base.visibility)
        return ModuleStatus(base.id, base.name, base.version, "NOT_INSTALLED",
                            f"Executable '{exe}' not found.", base.origin, base.visibility)
    # No probe defined: fall back to install marker.
    marker = stack_home.install_root() / manifest.id / ".sklab-installed"
    if marker.exists():
        return ModuleStatus(base.id, base.name, base.version, "READY",
                            "Install marker present.", base.origin, base.visibility)
    return ModuleStatus(base.id, base.name, base.version, "NOT_INSTALLED",
                        "Module is not installed.", base.origin, base.visibility)


def collect_statuses(registry: Registry) -> list[ModuleStatus]:
    out: list[ModuleStatus] = []
    for module_id in sorted(registry.modules.keys()):
        loaded = registry.modules[module_id]
        health = check_health(loaded.manifest)
        health.origin = loaded.origin
        out.append(health)
    return out


def base_tool_report() -> list[dict[str, str]]:
    tools = [
        ("python", [sys.executable, "--version"]),
        ("node", ["node", "--version"]),
        ("git", ["git", "--version"]),
        ("docker", ["docker", "--version"]),
    ]
    report: list[dict[str, str]] = []
    for name, argv in tools:
        if name == "python":
            report.append({"tool": name, "available": "yes", "version": platform.python_version()})
            continue
        result = run_command(argv, timeout=10.0)
        if result.not_found:
            report.append({"tool": name, "available": "no", "version": ""})
        elif result.ok:
            first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else name
            report.append({"tool": name, "available": "yes", "version": redact_text(first)[:120]})
        else:
            report.append({"tool": name, "available": "no", "version": ""})
    return report


def stack_doctor(registry: Registry) -> dict[str, object]:
    """Zero-cost health checks only. Never runs paid inference."""
    statuses = collect_statuses(registry)
    tools = base_tool_report()
    # Dependency consistency (resolver validation without installing).
    try:
        order = resolve(registry, include_optional=True).order
        consistency = {"ok": True, "order": order, "error": None}
    except ResolverError as exc:
        consistency = {"ok": False, "order": [], "error": f"[{exc.code}] {exc.message}"}
    # Writable dirs.
    dirs: list[dict[str, object]] = []
    for label, path in (
        ("home", stack_home.sklab_home()),
        ("config", stack_home.config_root()),
        ("modules.d", stack_home.modules_dir()),
        ("state", stack_home.state_dir()),
        ("cache", stack_home.cache_root()),
    ):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".sklab-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            dirs.append({"dir": label, "path": str(path), "writable": True})
        except OSError:
            dirs.append({"dir": label, "path": str(path), "writable": False})
    counts: dict[str, int] = {}
    for item in statuses:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "tools": tools,
        "modules": [
            {"id": s.id, "name": s.name, "version": s.version, "status": s.status,
             "detail": redact_text(s.detail), "origin": s.origin, "visibility": s.visibility}
            for s in statuses
        ],
        "dependency_consistency": consistency,
        "dirs": dirs,
        "summary": counts,
    }


def _filter_scope(registry: Registry, *, scope: str) -> Registry:
    """Scope 'public' keeps only public modules; 'all' keeps everything configured."""
    if scope == "all":
        return registry
    filtered = Registry()
    filtered.errors = list(registry.errors)
    for module_id, loaded in registry.modules.items():
        if loaded.manifest.visibility == "public":
            filtered.modules[module_id] = loaded
    return filtered


def plan_setup(registry: Registry, *, scope: str = "public") -> tuple[list[str], list[SetupPlanStep]]:
    scoped = _filter_scope(registry, scope=scope)
    result = resolve(scoped, include_optional=(scope == "all"))
    steps: list[SetupPlanStep] = []
    for module_id in result.order:
        manifest = scoped.modules[module_id].manifest
        missing = adapters.missing_base_tool(manifest.install.type)
        if missing is not None:
            steps.append(SetupPlanStep(
                id=module_id, action="unavailable",
                reason=f"Base tool '{missing}' is not installed.",
                argv_preview=adapters.plan_install(manifest),
            ))
            continue
        health = check_health(manifest)
        if health.status == "READY":
            steps.append(SetupPlanStep(
                id=module_id, action="skip", reason="Already READY (idempotent).",
                argv_preview=[],
            ))
        else:
            steps.append(SetupPlanStep(
                id=module_id, action="install",
                reason=f"Status is {health.status}; install/verify.",
                argv_preview=adapters.plan_install(manifest),
            ))
    return result.order, steps


def run_setup(
    registry: Registry,
    *,
    scope: str = "public",
    dry_run: bool = False,
    state_path: Path | None = None,
) -> SetupResult:
    scoped = _filter_scope(registry, scope=scope)
    stack_home.ensure_layout()
    order, _plan = plan_setup(registry, scope=scope)
    state = load_state(state_path)
    results: dict[str, AdapterResult] = {}
    health: dict[str, ModuleStatus] = {}
    for module_id in order:
        loaded: LoadedManifest = scoped.modules[module_id]
        manifest = loaded.manifest
        current = check_health(manifest)
        if current.status == "READY" and not dry_run:
            # Idempotent: do not reinstall a healthy module; refresh state timestamp.
            record_module(
                state, module_id=module_id, version=manifest.version,
                install_type=manifest.install.type, origin=loaded.origin,
                manifest_fingerprint=loaded.fingerprint or manifest.fingerprint(),
                status="READY", health="READY",
            )
            results[module_id] = AdapterResult(
                module_id=module_id, ok=True, status="SKIPPED",
                message=f"'{module_id}' already READY; skipped (idempotent).",
                steps=[],
            )
            current.origin = loaded.origin
            health[module_id] = current
            continue
        adapter_result = adapters.install_module(manifest, dry_run=dry_run)
        results[module_id] = adapter_result
        if not dry_run:
            after = check_health(manifest)
            after.origin = loaded.origin
            health[module_id] = after
            record_module(
                state, module_id=module_id, version=manifest.version,
                install_type=manifest.install.type, origin=loaded.origin,
                manifest_fingerprint=loaded.fingerprint or manifest.fingerprint(),
                status=after.status, health=after.status,
            )
        else:
            current.origin = loaded.origin
            health[module_id] = current
    if not dry_run:
        save_state(state, state_path)
    summary: dict[str, int] = {}
    for item in health.values():
        summary[item.status] = summary.get(item.status, 0) + 1
    # Also count adapter SKIPPED outcomes under their own label for the human summary.
    skipped_installs = sum(1 for r in results.values() if r.status in ("SKIPPED", "UNAVAILABLE"))
    if skipped_installs:
        summary["SKIPPED_INSTALLS"] = skipped_installs
    return SetupResult(order=order, results=results, health=health, summary=summary)


def plan_update(registry: Registry, *, state_path: Path | None = None) -> list[dict[str, str]]:
    state = load_state(state_path)
    order = resolve(registry, include_optional=True).order
    plan: list[dict[str, str]] = []
    for module_id in order:
        loaded = registry.modules[module_id]
        manifest = loaded.manifest
        recorded = state.modules.get(module_id)
        if recorded is None:
            plan.append({"id": module_id, "action": "install", "reason": "Not previously installed."})
        elif recorded.version != manifest.version:
            plan.append({
                "id": module_id,
                "action": "update",
                "reason": f"Version {recorded.version or '?'} -> {manifest.version}.",
            })
        elif recorded.manifest_fingerprint and loaded.fingerprint:
            if recorded.manifest_fingerprint != loaded.fingerprint:
                plan.append({"id": module_id, "action": "update", "reason": "Manifest changed."})
            else:
                plan.append({"id": module_id, "action": "skip", "reason": "Already up to date."})
        else:
            plan.append({"id": module_id, "action": "skip", "reason": "Already up to date."})
    return plan


def clean_preview() -> list[dict[str, str]]:
    """List SKLab-owned cleanable paths only. Never user repos or run history."""
    candidates: list[dict[str, str]] = []
    roots = [stack_home.cache_root(), stack_home.logs_dir(), stack_home.install_root()]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and (
                path.suffix in (".tmp", ".log", ".cache") or ".tmp" in path.name or path.name.startswith(".sklab-tmp")
            ):
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                candidates.append({"path": str(path), "size_bytes": str(size)})
    # Stale download/build temp explicitly owned by the installer.
    tmp_hint = stack_home.sklab_home() / "tmp"
    if tmp_hint.exists():
        for path in sorted(tmp_hint.rglob("*")):
            if path.is_file():
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                candidates.append({"path": str(path), "size_bytes": str(size)})
    return candidates


def run_clean(*, dry_run: bool = False) -> dict[str, object]:
    targets = clean_preview()
    removed = 0
    if not dry_run:
        for item in targets:
            try:
                Path(item["path"]).unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
    return {"dry_run": dry_run, "candidates": targets, "removed": removed if not dry_run else 0}
