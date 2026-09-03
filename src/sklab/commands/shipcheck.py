"""``sklab shipcheck``: release/readiness verification with meaningful exit codes.

Exit codes: 0 = READY, 1 = READY_WITH_WARNINGS, 2 = NOT_READY, 3 = CLI/internal error.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.release.models import ShipReport, Verdict, exit_code_for
from sklab.release.planner import describe_plan, plan_for_path
from sklab.release.runner import run_shipcheck


def register(app: typer.Typer) -> None:
    @app.command("shipcheck")
    def shipcheck(
        path: Path | None = typer.Option(None, "--path", help="Repository path to check (default: current directory)."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show the planned checks without executing them."),
        timeout: float = typer.Option(600.0, "--timeout", help="Per-command timeout in seconds."),
    ) -> None:
        """Check whether a repository looks ready for release/deployment."""
        try:
            root = (path or Path.cwd()).resolve()
            if timeout <= 0:
                raise SklabError("CONFIG_ERROR", "Timeout must be a positive number of seconds.")
            if dry_run:
                _dry_run(root, json_output)
                return
            report = run_shipcheck(root, timeout_per_command=timeout)
            code = exit_code_for(report.verdict)
            if json_output:
                output.print_json(report.to_dict())
                raise typer.Exit(code=code)
            _render(report)
            raise typer.Exit(code=code)
        except typer.Exit:
            raise
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)


def _dry_run(root: Path, json_output: bool) -> None:
    info, steps = plan_for_path(root)
    if json_output:
        output.print_json(
            {
                "root": str(info.root),
                "technologies": info.technologies,
                "dry_run": True,
                "plan": [
                    {"id": s.id, "name": s.name, "argv": s.argv, "kind": s.kind, "description": s.description}
                    for s in steps
                ],
            }
        )
        return
    console = output.get_console()
    console.print("[bold]SKLab Ship Check (dry run)[/bold]\n")
    console.print("Planned checks:\n")
    for line in describe_plan(steps):
        console.print(f"  {line}")
    console.print("\nNo commands were executed.")


def _render(report: ShipReport) -> None:
    console = output.get_console()
    console.print("[bold]SKLab Ship Check[/bold]\n")
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Details")
    for check in report.checks:
        status_text = output.styled_status(check.status.value)
        table.add_row(check.name, status_text, check.message)
    console.print(table)
    verdict_style = output.STATUS_STYLES.get(report.verdict.value, "bold")
    if console.no_color:
        console.print(f"\nVerdict: {report.verdict.value}")
    else:
        console.print(f"\nVerdict:\n[{verdict_style}]{report.verdict.value}[/{verdict_style}]")
    if report.verdict == Verdict.NOT_READY:
        console.print("\nFix the FAIL items above, then re-run shipcheck.", style="red")
