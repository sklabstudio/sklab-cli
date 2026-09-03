"""``sklab cache``: inspect and manage the local resource cache (safe by design)."""

from __future__ import annotations

import typer

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.config import load_config
from sklab.core.errors import SklabError
from sklab.resources.cache import SklabCache

app = typer.Typer(help="Inspect or clear the SKLab resource cache.", no_args_is_help=True)


@app.command("status")
def status(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show cache location and size."""
    try:
        data = SklabCache().status()
        if json_output:
            output.print_json(data)
            return
        console = output.get_console()
        console.print("[bold]SKLab cache[/bold]\n")
        console.print(f"Location   {data['location']}")
        console.print(f"Size       {data['size_bytes']} bytes in {data['files']} file(s)")
        entries = data["entries"]
        if entries:
            console.print(f"Entries    {', '.join(entries)}")
        else:
            console.print("Entries    (empty)")
    except SklabError as exc:
        fail(exc, json_mode=json_output)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc, json_mode=json_output)


@app.command("clear")
def clear(
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Delete everything inside the SKLab cache directory (nothing else)."""
    try:
        cache = SklabCache()
        info = cache.status()
        if not yes and not json_output:
            typer.confirm(f"Clear the SKLab cache at {info['location']}?", abort=True)
        result = cache.clear()
        if json_output:
            output.print_json(result)
            return
        output.success(f"Cache cleared ({result['removed_files']} file(s) removed).")
    except typer.Abort:
        output.warning("Cache clear aborted.")
        raise typer.Exit(code=1) from None
    except SklabError as exc:
        fail(exc, json_mode=json_output)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc, json_mode=json_output)


@app.command("refresh")
def refresh() -> None:
    """Re-resolve cached Coding Lab content (works offline for local sources)."""
    try:
        cfg = load_config()
        result = SklabCache().refresh(
            coding_lab_source=cfg.coding_lab_source, timeout=cfg.network_timeout, cache_ttl=cfg.cache_ttl
        )
        output.success(f"Cache refreshed. Coding Lab: {result['coding_lab']}.")
    except SklabError as exc:
        fail(exc)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc)
