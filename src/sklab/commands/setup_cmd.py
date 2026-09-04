"""``sklab setup``: idempotent workstation setup with dry-run planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.stack import home as stack_home
from sklab.stack.adapters import AdapterResult
from sklab.stack.operations import ModuleStatus, SetupPlanStep, plan_setup, run_setup
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
        yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
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

            if dry_run:
                if json_output:
                    output.print_json({
                        "scope": scope,
                        "dry_run": True,
                        "order": order,
                        "plan": [
                            {"id": s.id, "action": s.action, "reason": redact_text(s.reason),
                             "argv_preview": [list(a) for a in s.argv_preview]}
                            for s in steps
                        ],
                    })
                    return
                _render_plan(scope, order, steps)
                return

            if not yes and not json_output:
                _render_plan(scope, order, steps)
                typer.confirm("Proceed with setup?", abort=True)

            result = run_setup(registry, scope=scope, dry_run=False)
            if json_output:
                output.print_json({
                    "scope": scope,
                    "dry_run": False,
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
                })
                return
            _render_result(scope, result.order, result.results, result.health, result.summary)
        except typer.Abort:
            output.warning("Setup aborted.")
            raise typer.Exit(code=1) from None
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)


def _render_plan(scope: str, order: list[str], steps: Sequence[SetupPlanStep]) -> None:
    console = output.get_console()
    console.print(f"[bold]SKLab setup plan (scope: {scope}, dry run)[/bold]\n")
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Order", style="bold")
    table.add_column("Module")
    table.add_column("Action")
    table.add_column("Reason")
    for index, step in enumerate(steps, start=1):
        table.add_row(str(index), step.id, step.action, redact_text(step.reason))
    console.print(table)
    console.print(f"\nDependency order: {', '.join(order) if order else '(none)'}")
    console.print("No changes were made.")


def _render_result(
    scope: str,
    order: list[str],
    results: Mapping[str, AdapterResult],
    health: Mapping[str, ModuleStatus],
    summary: Mapping[str, int],
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
    console.print(f"Home: {stack_home.sklab_home()}")
