"""Stack operations: setup planning/execution, status, doctor, update, clean."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sklab.core.subprocess import run_command
from sklab.stack import adapters, preflight
from sklab.stack import home as stack_home
from sklab.stack.adapters import AdapterResult, auth_required_for
from sklab.stack.manifest import ModuleManifest
from sklab.stack.redaction import redact_text
from sklab.stack.registry import LoadedManifest, Registry
from sklab.stack.resolver import ResolverError, resolve
from sklab.stack.runlog import append_event, new_run_log
from sklab.stack.state import load_state, record_module, save_state

HEALTH_TIMEOUT = 15.0
HEALTH_STATUSES = ("READY", "DEGRADED", "FAILED", "NOT_INSTALLED", "UNAVAILABLE", "UNKNOWN", "AUTH_REQUIRED")


class DiskSafetyError(Exception):
    """Raised before any mutation when free disk is dangerously low."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "LOW_DISK"
        self.message = message


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
    log_path: str = ""
    preflight: dict[str, object] = field(default_factory=dict)
    resume_hint: str = ""


def describe_host() -> dict[str, object]:
    host = preflight.host_info()
    verdict = preflight.resource_verdict(host)
    return {
        "os": host.os_name,
        "cpu": host.cpu_count,
        "ram_mib": host.ram_mib,
        "swap_mib": host.swap_mib,
        "disk_free_mb": host.disk_free_mb,
        "python": host.python_version,
        "node": host.node_version,
        "resource_level": verdict.level,
        "resource_warnings": verdict.warnings,
    }


def check_health(manifest: ModuleManifest) -> ModuleStatus:
    base = ModuleStatus(
        id=manifest.id, name=manifest.name, version=manifest.version,
        status="UNKNOWN", origin="", visibility=manifest.visibility,
    )
    if auth_required_for(manifest):
        # Missing credentials for a private source: report honestly, never crash.
        marker = stack_home.install_root() / manifest.id / ".sklab-installed"
        if marker.exists():
            return ModuleStatus(base.id, base.name, base.version, "READY",
                                "Install marker present.", base.origin, base.visibility)
        return ModuleStatus(base.id, base.name, base.version, "AUTH_REQUIRED",
                            f"Authenticated access required (${manifest.source.url_env or 'git auth'}). "
                            "Run 'gh auth login'; public install continues.",
                            base.origin, base.visibility)
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
    """Zero-cost health checks only. Never runs paid inference. Never mutates."""
    statuses = collect_statuses(registry)
    tools = base_tool_report()
    try:
        order = resolve(registry, include_optional=True).order
        consistency = {"ok": True, "order": order, "error": None}
    except ResolverError as exc:
        consistency = {"ok": False, "order": [], "error": f"[{exc.code}] {exc.message}"}
    dirs: list[dict[str, object]] = []
    for label, path in (
        ("home", stack_home.sklab_home()),
        ("config", stack_home.config_root()),
        ("modules.d", stack_home.modules_dir()),
        ("state", stack_home.state_dir()),
        ("cache", stack_home.cache_root()),
        ("repos", stack_home.repos_dir()),
        ("runtime", stack_home.runtime_dir()),
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
    host = preflight.host_info()
    verdict = preflight.resource_verdict(host)
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "tools": tools,
        "base_deps": preflight.detect_base_deps(),
        "path": preflight.path_status(),
        "path_fix": preflight.path_fix_plan(),
        "docker": preflight.check_docker(),
        "node": preflight.check_node(),
        "github_auth": preflight.check_github_auth(),
        "resources": {
            "cpu": host.cpu_count,
            "ram_mib": host.ram_mib,
            "swap_mib": host.swap_mib,
            "disk_free_mb": host.disk_free_mb,
            "level": verdict.level,
            "warnings": verdict.warnings,
        },
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
        if auth_required_for(manifest):
            steps.append(SetupPlanStep(
                id=module_id, action="auth",
                reason=f"Private module needs ${manifest.source.url_env or 'git auth'} (gh auth login).",
                argv_preview=[],
            ))
            continue
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
        elif health.status == "AUTH_REQUIRED":
            steps.append(SetupPlanStep(
                id=module_id, action="auth", reason=health.detail,
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
    apply_path_fix: bool = False,
    log_path: Path | None = None,
) -> SetupResult:
    """Idempotent, resumable setup. Dry-run performs zero mutation (no log file either... almost).

    Transaction semantics: successful safe installations are preserved, failed
    modules are marked precisely, successful modules are never redone, and the
    summary carries resume instructions. No risky global rollback.
    """
    scoped = _filter_scope(registry, scope=scope)
    host = describe_host()
    to_install = scope  # for the log record
    if dry_run:
        order, _plan = plan_setup(registry, scope=scope)
        # Dry-run may inspect only: still create no log file, no state, no dirs beyond reads.
        health: dict[str, ModuleStatus] = {}
        for module_id in order:
            loaded = scoped.modules[module_id]
            current = check_health(loaded.manifest)
            current.origin = loaded.origin
            health[module_id] = current
        summary: dict[str, int] = {}
        for item in health.values():
            summary[item.status] = summary.get(item.status, 0) + 1
        return SetupResult(order=order, results={}, health=health, summary=summary, preflight=host)

    stack_home.ensure_layout()
    log = log_path or new_run_log("setup")
    append_event(log, "setup_start", {"scope": to_install, "host": host})
    order, plan = plan_setup(registry, scope=scope)

    # Disk safety gate before any heavy work: abort before partial installation.
    install_ids = [step.id for step in plan if step.action == "install"]
    if install_ids:
        heavy = sum(
            1 for mid in install_ids
            if scoped.modules[mid].manifest.install.type in preflight.HEAVY_INSTALL_TYPES
        )
        required = preflight.estimate_plan_mb(heavy, len(install_ids) - heavy)
        ok, detail = preflight.check_disk_ok(required, path=str(stack_home.repos_dir()))
        append_event(log, "disk_gate", {"required_mb": required, "detail": detail, "ok": ok})
        if not ok:
            append_event(log, "setup_aborted", {"reason": "low_disk"})
            raise DiskSafetyError(detail)

    if apply_path_fix:
        fix = preflight.apply_path_fix()
        append_event(log, "path_fix", dict(fix))

    state = load_state(state_path)
    results: dict[str, AdapterResult] = {}
    health_map: dict[str, ModuleStatus] = {}
    for module_id in order:
        loaded_module: LoadedManifest = scoped.modules[module_id]
        manifest = loaded_module.manifest
        append_event(log, "module_start", {"id": module_id})
        current = check_health(manifest)
        if current.status == "READY":
            # Idempotent: do not reinstall a healthy module; refresh state timestamp.
            record_module(
                state, module_id=module_id, version=manifest.version,
                install_type=manifest.install.type, origin=loaded_module.origin,
                manifest_fingerprint=loaded_module.fingerprint or manifest.fingerprint(),
                status="READY", health="READY",
            )
            results[module_id] = AdapterResult(
                module_id=module_id, ok=True, status="SKIPPED",
                message=f"'{module_id}' already READY; skipped (idempotent).",
                steps=[],
            )
            current.origin = loaded_module.origin
            health_map[module_id] = current
            append_event(log, "module_skip", {"id": module_id, "reason": "READY"})
            continue
        if current.status == "AUTH_REQUIRED":
            results[module_id] = AdapterResult(
                module_id=module_id, ok=False, status="AUTH_REQUIRED",
                message=current.detail, steps=[], auth_required=True,
            )
            current.origin = loaded_module.origin
            health_map[module_id] = current
            record_module(
                state, module_id=module_id, version=manifest.version,
                install_type=manifest.install.type, origin=loaded_module.origin,
                manifest_fingerprint=loaded_module.fingerprint or manifest.fingerprint(),
                status="AUTH_REQUIRED", health="AUTH_REQUIRED",
            )
            append_event(log, "module_auth_required", {"id": module_id})
            continue
        adapter_result = adapters.install_module(manifest, dry_run=False)
        results[module_id] = adapter_result
        after = check_health(manifest)
        after.origin = loaded_module.origin
        health_map[module_id] = after
        record_module(
            state, module_id=module_id, version=manifest.version,
            install_type=manifest.install.type, origin=loaded_module.origin,
            manifest_fingerprint=loaded_module.fingerprint or manifest.fingerprint(),
            status=after.status, health=after.status,
        )
        append_event(log, "module_done", {
            "id": module_id, "install_status": adapter_result.status,
            "health": after.status, "changed": adapter_result.changed,
        })
    save_state(state, state_path)
    summary_counts: dict[str, int] = {}
    for item in health_map.values():
        summary_counts[item.status] = summary_counts.get(item.status, 0) + 1
    skipped_installs = sum(1 for r in results.values() if r.status in ("SKIPPED", "UNAVAILABLE"))
    if skipped_installs:
        summary_counts["SKIPPED_INSTALLS"] = skipped_installs
    failed = sorted([mid for mid, h in health_map.items() if h.status in ("FAILED", "DEGRADED")])
    auth_pending = sorted([mid for mid, h in health_map.items() if h.status == "AUTH_REQUIRED"])
    # Adapter claimed success but post-install health disagrees: never fake READY, flag for resume.
    mismatched = sorted([
        mid for mid, h in health_map.items()
        if h.status in ("NOT_INSTALLED", "UNKNOWN") and results.get(mid) is not None and results[mid].ok
    ])
    resume_hint = ""
    if failed or auth_pending or mismatched:
        parts = []
        if failed:
            parts.append(f"failed: {', '.join(failed)} - fix the cause and re-run 'sklab setup --all' to resume")
        if mismatched:
            parts.append(
                f"unverified: {', '.join(mismatched)} - install reported success but health is not READY; "
                "re-run 'sklab setup --all' to retry"
            )
        if auth_pending:
            parts.append(f"auth required: {', '.join(auth_pending)} - 'gh auth login', then re-run")
        resume_hint = "; ".join(parts) + ". Successful modules are preserved and will be skipped."
    append_event(log, "setup_done", {"summary": summary_counts, "resume_hint": resume_hint})
    _ = os.environ.get("SKLAB_SETUP_NOTE", "")
    return SetupResult(
        order=order, results=results, health=health_map, summary=summary_counts,
        log_path=str(log), preflight=host, resume_hint=resume_hint,
    )


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
