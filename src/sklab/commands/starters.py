"""``sklab starters``: list available project starters."""

from __future__ import annotations

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.config import load_config
from sklab.core.errors import SklabError
from sklab.starters.provider import get_provider


def register(app: typer.Typer) -> None:
    @app.command("starters")
    def starters(
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
        source: str | None = typer.Option(None, "--source", help="Starter source: local path or owner/repo[@branch]."),
        branch: str | None = typer.Option(None, "--branch", help="Branch for remote starter sources."),
    ) -> None:
        """List available project starters."""
        try:
            cfg = load_config()
            provider = get_provider(
                source or cfg.starters_source,
                branch=branch or cfg.default_branch,
                timeout=cfg.network_timeout,
                cache_ttl=cfg.cache_ttl,
            )
            items = provider.list_starters()
            if json_output:
                starters = [
                    {"name": s.name, "description": s.description, "available": s.available} for s in items
                ]
                output.print_json({"source": provider.describe(), "starters": starters})
                return
            console = output.get_console()
            console.print("[bold]Available starters[/bold]\n")
            table = Table(show_header=False, box=None, pad_edge=False)
            table.add_column("Name", style="bold cyan")
            table.add_column("Description")
            for item in items:
                suffix = "" if item.available else "  (not in this source)"
                table.add_row(item.name, item.description + suffix)
            console.print(table)
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)
