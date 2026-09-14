"""``sklab setup``: real idempotent VPS bootstrap with dry-run planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.stack import home as stack_home
from sklab.stack import preflight
from sklab.stack.adapters import AdapterResult
from sklab.stack.operations import (
    DiskSafetyError,
    ModuleStatus,
    SetupPlanStep,
    describe_host,
    plan_setup,
    run_setup,
)
from sklab.stack.redaction import redact_text
from sklab.stack.registry import load_registry
from sklab.stack.resolver import ResolverError


def register(app: typer.Typer) -> None:
    @app.command("setup")
    def setup(
        all_modules: bool = typer.Option(False, "--all", help="Install public + optional locally-registered modules."),
        public: bool = typer.Option(False, "--public", help="Install only public modules."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show the exact plan without installing."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
        yes: bool = typer.Option(False, "--yes", help="Skip confirmation prompts (automation/CI/VPS bootstrap)."),
        fix_path: bool = typer.Option(False, "--fix-path", help="Allow idempotent shell PATH bootstrap when needed."),
    ) -> None:
        """Set up the SKLab workstation (idempotent; safe to re-run)."""
        try:
            if all_modules and public:
                raise SklabError("CONFIG_ERROR", "Pass either --all or --public, not both.")
            scope = "all" if all_modules else "public"
            registry = load_registry()
            try:
                order, steps = plan_setup(registry, scope=scope)
            except ResolverError as exc:
                raise SklabError(exc.code, exc.message) from exc
            host = describe_host()

            if dry_run:
                if json_output:
                    output.print_json({
                        "scope": scope,
                        "dry_run": True,
                        "host": host,
                        "order": order,
                        "plan": [
                            {"id": s.id, "action": s.action, "reason": redact_text(s.reason),
                             "argv_preview": [list(a) for a in s.argv_preview]}
                            for s in steps
                        ],
                    })
                    return
                _render_plan(scope, order, steps, host)
                return

            installs = sum(1 for s in steps if s.action == "install")
            if not yes and not json_output:
                _render_plan(scope, order, steps, host, dry=False)
                _maybe_report_prereqs(json_output=False)
                typer.confirm(f"Proceed with {installs} installs?", abort=True)

            try:
                result = run_setup(registry, scope=scope, dry_run=False, apply_path_fix=(fix_path or yes))
            except DiskSafetyError as exc:
                raise SklabError("LOW_DISK", redact_text(exc.message)) from exc
            if json_output:
                output.print_json({
                    "scope": scope,
                    "dry_run": False,
                    "host": host,
                    "order": result.order,
                    "results": {
                        mid: {"ok": r.ok, "status": r.status, "message": redact_text(r.message)}
                        for mid, r in result.results.items()
                    },
                    "health": {
                        mid: {"status": h.status, "detail": redact_text(h.detail)}
                        for mid, h in result.health.items()
                    },
                    "summary": result.summary,
                    "home": str(stack_home.sklab_home()),
                    "repos": str(stack_home.repos_dir()),
                    "log": result.log_path,
                    "resume_hint": result.resume_hint,
                })
                return
            _render_result(scope, result.order, result.results, result.health, result.summary,
                           result.log_path, result.resume_hint)
            # Post-setup equivalents, as specified: status + doctor guidance.
            output.info("Next: 'sklab status' and 'sklab doctor --stack' (ran automatically above).")
        except typer.Abort:
            output.warning("Setup aborted.")
            raise typer.Exit(code=1) from None
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)


def _maybe_report_prereqs(*, json_output: bool) -> None:
    if json_output:
        return
    deps = preflight.detect_base_deps()
    missing = [d["name"] for d in deps if d["available"] == "no" and d["name"] not in ("gh",)]
    if not missing:
        return
    console = output.get_console()
    console.print("\n[bold]Missing prerequisites:[/bold] " + ", ".join(missing))
    if preflight.is_ubuntu():
        apt_names = sorted({d.get("apt", "") for d in deps if d["name"] in missing} - {""})
        if apt_names:
            console.print("On Ubuntu, install after review, e.g.: sudo apt-get install -y " + " ".join(apt_names))
        console.print("Setup never apt-installs without your explicit confirmation above.")
    path_plan = preflight.path_fix_plan()
    if path_plan:
        console.print(f"\nPATH: {preflight.user_bin_dir()} is not on PATH. "
                      f"Re-run with --fix-path (or --yes) to append idempotently to {path_plan[0]['file']}.")


def _render_plan(
    scope: str, order: list[str], steps: Sequence[SetupPlanStep], host: Mapping[str, object], dry: bool = True
) -> None:
    console = output.get_console()
    title = f"SKLab setup plan (scope: {scope}, dry run)" if dry else f"SKLab Setup (scope: {scope})"
    console.print(f"[bold]{title}[/bold]\n")
    console.print("Host:")
    console.print(f"  {host.get('os', '')}")
    ram_raw, swap_raw, disk_raw = host.get("ram_mib", 0), host.get("swap_mib", 0), host.get("disk_free_mb", 0)
    ram = ram_raw if isinstance(ram_raw, int) else 0
    swap = swap_raw if isinstance(swap_raw, int) else 0
    disk = disk_raw if isinstance(disk_raw, int) else 0
    if ram:
        console.print(
            f"  CPU: {host.get('cpu', '?')}  RAM: {ram / 1024:.1f} GiB  "
            f"Swap: {swap / 1024:.1f} GiB  Disk free: {disk} MiB"
        )
    console.print(f"  Python: {host.get('python', '')}  Node: {host.get('node', '') or 'not installed'}")
    warnings_raw = host.get("resource_warnings", [])
    warnings: Sequence[object] = warnings_raw if isinstance(warnings_raw, list) else []
    for warning in warnings:
        console.print(f"  Note: {warning}")
    console.print("\nPlan:")
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column("Status", style="bold")
    table.add_column("Module")
    for step in steps:
        short = {"skip": "READY", "install": "INSTALL", "unavailable": "SKIP", "auth": "AUTH"}.get(step.action)
        label = short if short is not None else step.action.upper()
        table.add_row(f"  {label}", step.id)
    console.print(table)
    auth = [s.id for s in steps if s.action == "auth"]
    if auth:
        console.print(f"\nPrivate (auth required, skipped safely): {', '.join(auth)} - 'gh auth login' to enable.")
    if dry:
        console.print(f"\nDependency order: {', '.join(order) if order else '(none)'}")
        console.print("No changes were made (dry run: no clone/fetch/install/docker/apt/PATH/service).")


def _render_result(
    scope: str,
    order: list[str],
    results: Mapping[str, AdapterResult],
    health: Mapping[str, ModuleStatus],
    summary: Mapping[str, int],
    log_path: str,
    resume_hint: str,
) -> None:
    console = output.get_console()
    console.print(f"[bold]SKLab setup (scope: {scope})[/bold]\n")
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Module", style="bold")
    table.add_column("Install")
    table.add_column("Health")
    table.add_column("Details")
    for module_id in order:
        res = results.get(module_id)
        item = health.get(module_id)
        table.add_row(
            module_id,
            res.status if res else "-",
            output.styled_status(item.status) if item else "-",
            redact_text(res.message if res else ""),
        )
    console.print(table)
    parts = [f"{key}: {value}" for key, value in sorted(summary.items())]
    console.print(f"\nSummary: {'; '.join(parts) if parts else 'no modules'}")
    console.print(f"Home: {stack_home.sklab_home()}  Repos: {stack_home.repos_dir()}")
    if log_path:
        console.print(f"Log: {log_path}")
    if resume_hint:
        console.print(f"\nResume: {resume_hint}")
    else:
        console.print("\nAll requested modules are READY or cleanly skipped. Re-run anytime to resume/repair.")
