"""``sklab doctor``: read-only environment/repository diagnostics."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.diagnostics.checks import run_doctor
from sklab.diagnostics.models import CheckStatus


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor(
        path: Path | None = typer.Option(
            None, "--path", help="Repository path to inspect (default: current directory)."
        ),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Inspect the environment and repository without changing anything."""
        try:
            root = (path or Path.cwd()).resolve()
            info, checks = run_doctor(root)
            if json_output:
                output.print_json(
                    {
                        "root": str(info.root),
                        "technologies": info.technologies,
                        "checks": [c.to_dict() for c in checks],
                    }
                )
                return
            console = output.get_console()
            console.print("[bold]SKLab Doctor[/bold]\n")
            table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
            table.add_column("Check", style="bold")
            table.add_column("Status")
            table.add_column("Details")
            for check in checks:
                status_text = output.styled_status(check.status.value)
                table.add_row(check.name, status_text, check.message)
            console.print(table)
            remediations = [c for c in checks if c.remediation and c.status in (CheckStatus.WARNING, CheckStatus.FAIL)]
            if remediations:
                console.print("\n[bold]Suggested fixes:[/bold]")
                for check in remediations:
                    console.print(f"  {check.name}: {check.remediation}")
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)
