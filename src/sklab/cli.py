"""SKLab CLI entry point: ``sklab``."""

from __future__ import annotations

import platform
import sys

import typer

from sklab import __version__
from sklab.commands import cache_cmd, config_cmd, doctor, init, prompts, shipcheck, starters, workflows
from sklab.core import output, paths
from sklab.core.config import KEYS, load_config

app = typer.Typer(
    name="sklab",
    help="Developer workflows, project starters, diagnostics, and release checks from SKLab Studio.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        print(f"sklab {__version__}")
        raise typer.Exit(0)


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed output and tracebacks."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress non-essential output."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable colored output."),
) -> None:
    output.configure_output(verbose=verbose, quiet=quiet, no_color=no_color)
    ctx.obj = {"verbose": verbose, "quiet": quiet, "no_color": no_color}


init.register(app)
doctor.register(app)
shipcheck.register(app)
starters.register(app)
prompts.register(app)
workflows.register(app)

app.add_typer(config_cmd.app, name="config")
app.add_typer(cache_cmd.app, name="cache")


@app.command("info")
def info(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show CLI version, runtime, and filesystem locations."""
    from sklab.commands.common import handle_unexpected

    try:
        cfg = load_config()
        data: dict[str, object] = {
            "sklab": __version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "config_file": str(paths.config_file()),
            "cache_dir": str(paths.cache_dir()),
            "config": {k: getattr(cfg, k) for k in KEYS},
        }
        if json_output:
            output.print_json(data)
            return
        console = output.get_console()
        console.print("[bold]SKLab info[/bold]\n")
        console.print(f"SKLab CLI      {__version__}")
        console.print(f"Python         {platform.python_version()} ({sys.executable})")
        console.print(f"Platform       {platform.platform()}")
        console.print(f"Config         {paths.config_file()}")
        console.print(f"Cache          {paths.cache_dir()}")
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc, json_mode=json_output)


if __name__ == "__main__":
    app()
