"""``sklab prompts`` / ``sklab prompt``: browse and retrieve Coding Lab prompts."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.clipboard import copy_to_clipboard
from sklab.core.config import load_config
from sklab.core.errors import SklabError
from sklab.resources.coding_lab import CodingLab


def register(app: typer.Typer) -> None:
    @app.command("prompts")
    def prompts(
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
        source: str | None = typer.Option(None, "--source", help="Coding Lab source: local path or owner/repo."),
        refresh: bool = typer.Option(False, "--refresh", help="Refresh the cached Coding Lab copy."),
    ) -> None:
        """List available Coding Lab prompts."""
        try:
            lab = _lab(source, refresh)
            items = lab.list_prompts(refresh=refresh)
            if json_output:
                output.print_json({"source": lab.describe(), "prompts": [r.to_dict() for r in items]})
                return
            console = output.get_console()
            console.print("[bold]Available prompts[/bold]\n")
            if not items:
                console.print("No prompts found in this source.")
                return
            table = Table(show_header=False, box=None, pad_edge=False)
            table.add_column("Name", style="bold cyan")
            for item in items:
                table.add_row(item.name)
            console.print(table)
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)

    @app.command("prompt")
    def prompt(
        name: str = typer.Argument(..., help="Prompt name, e.g. audit-repository."),
        output_path: Path | None = typer.Option(None, "--output", help="Write the prompt to a file instead of stdout."),
        copy: bool = typer.Option(False, "--copy", help="Copy the prompt to the clipboard."),
        source: str | None = typer.Option(None, "--source", help="Coding Lab source: local path or owner/repo."),
        refresh: bool = typer.Option(False, "--refresh", help="Refresh the cached Coding Lab copy."),
    ) -> None:
        """Print a Coding Lab prompt (Markdown) to stdout."""
        try:
            lab = _lab(source, refresh)
            text = lab.read_resource("prompts", name, refresh=refresh)
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(text, encoding="utf-8")
                output.success(f"Prompt saved to {output_path}.")
            if copy:
                helper = copy_to_clipboard(text)
                output.success(f"Prompt copied to clipboard ({helper}).")
            if output_path is None and not copy:
                # Raw markdown to stdout so it can be piped; no Rich formatting.
                output.print_text(text)
        except SklabError as exc:
            fail(exc)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc)


def _lab(source: str | None, refresh: bool) -> CodingLab:
    cfg = load_config()
    return CodingLab(
        source=source or cfg.coding_lab_source,
        branch=cfg.default_branch,
        timeout=cfg.network_timeout,
        cache_ttl=0 if refresh else cfg.cache_ttl,
    )
