"""``sklab status``: workstation module health (never fakes READY)."""

from __future__ import annotations

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.stack.operations import collect_statuses
from sklab.stack.registry import load_registry


def register(app: typer.Typer) -> None:
    @app.command("status")
    def status(
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Show READY / DEGRADED / FAILED / NOT_INSTALLED / UNAVAILABLE / AUTH_REQUIRED per module."""
        try:
            registry = load_registry()
            items = collect_statuses(registry)
            if json_output:
                output.print_json({
                    "modules": [
                        {"id": s.id, "name": s.name, "version": s.version, "status": s.status,
                         "detail": s.detail, "origin": s.origin, "visibility": s.visibility}
                        for s in items
                    ]
                })
                return
            console = output.get_console()
            console.print("[bold]SKLab status[/bold]\n")
            table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
            table.add_column("Module", style="bold")
            table.add_column("Version")
            table.add_column("Status")
            for item in items:
                table.add_row(item.name, item.version, output.styled_status(item.status))
            console.print(table)
            pending = [s for s in items if s.status in ("NOT_INSTALLED", "UNAVAILABLE", "UNKNOWN", "AUTH_REQUIRED")]
            if pending:
                console.print(f"\n{len(pending)} module(s) not ready.")
                console.print("Run 'sklab setup --dry-run' for the install plan.")
                auth = [s for s in pending if s.status == "AUTH_REQUIRED"]
                if auth:
                    console.print(f"Auth required: {', '.join(s.id for s in auth)} — 'gh auth login'.")
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)
