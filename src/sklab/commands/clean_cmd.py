"""``sklab clean``: remove only SKLab-owned caches/temp (never user repos)."""

from __future__ import annotations

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.stack.operations import clean_preview, run_clean


def register(app: typer.Typer) -> None:
    @app.command("clean")
    def clean(
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed."),
        yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Clean SKLab-owned caches and installer temp (safe by default)."""
        try:
            if dry_run:
                preview = clean_preview()
                if json_output:
                    output.print_json({"dry_run": True, "candidates": preview})
                    return
                _render(preview, dry=True)
                return
            if not yes and not json_output:
                preview = clean_preview()
                _render(preview, dry=True)
                if not preview:
                    output.success("Nothing to clean.")
                    return
                typer.confirm("Remove the files listed above?", abort=True)
            result = run_clean(dry_run=False)
            if json_output:
                output.print_json(result)
                return
            candidates_raw = result.get("candidates")
            candidates: list[dict[str, str]] = candidates_raw if isinstance(candidates_raw, list) else []
            removed_raw = result.get("removed")
            removed = int(removed_raw) if isinstance(removed_raw, (int, str)) else 0
            _render(candidates, dry=False, removed=removed)
        except typer.Abort:
            output.warning("Clean aborted.")
            raise typer.Exit(code=1) from None
        except typer.Exit:
            raise
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)


def _render(candidates: list[dict[str, str]], *, dry: bool, removed: int = 0) -> None:
    console = output.get_console()
    title = "SKLab clean (dry run)" if dry else "SKLab clean"
    console.print(f"[bold]{title}[/bold]\n")
    if not candidates:
        console.print("No SKLab-owned temp/cache files found. User repos and run history are never touched.")
        return
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Path", style="bold")
    table.add_column("Bytes")
    for item in candidates:
        table.add_row(item["path"], item["size_bytes"])
    console.print(table)
    if dry:
        console.print(f"\n{len(candidates)} file(s) would be removed. Nothing was deleted.")
    else:
        console.print(f"\nRemoved {removed} file(s). User repos and run history were preserved.")
