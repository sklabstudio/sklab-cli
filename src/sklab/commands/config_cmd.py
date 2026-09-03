"""``sklab config``: inspect and adjust CLI configuration."""

from __future__ import annotations

import typer

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output, paths
from sklab.core.config import KEYS, load_config, reset_config, set_value
from sklab.core.errors import SklabError

app = typer.Typer(help="Show or change SKLab CLI configuration.", no_args_is_help=True)


@app.command("show")
def show(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show the effective configuration (file + environment overrides)."""
    try:
        cfg = load_config()
        data = {"config_file": str(paths.config_file()), **{k: getattr(cfg, k) for k in KEYS}}
        if json_output:
            output.print_json(data)
            return
        console = output.get_console()
        console.print("[bold]SKLab configuration[/bold]\n")
        console.print(f"File: {paths.config_file()}\n")
        for key in KEYS:
            console.print(f"{key:<18} {getattr(cfg, key)}")
        console.print("\nEnvironment overrides: SKLAB_STARTERS_SOURCE, SKLAB_CODING_LAB_SOURCE,")
        console.print("SKLAB_DEFAULT_BRANCH, SKLAB_NETWORK_TIMEOUT, SKLAB_CACHE_TTL.")
    except SklabError as exc:
        fail(exc, json_mode=json_output)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc, json_mode=json_output)


@app.command("get")
def get(key: str = typer.Argument(..., help="Config key.")) -> None:
    """Print a single config value."""
    try:
        cfg = load_config()
        if key not in KEYS:
            raise SklabError("CONFIG_ERROR", f"Unknown config key: {key}. Valid keys: {', '.join(KEYS)}.")
        print(getattr(cfg, key))
    except SklabError as exc:
        fail(exc)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc)


@app.command("set")
def set_key(
    key: str = typer.Argument(..., help="Config key."),
    value: str = typer.Argument(..., help="New value."),
) -> None:
    """Set a config value in the user config file."""
    try:
        cfg = set_value(key, value)
        output.success(f"Set {key} = {getattr(cfg, key)} ({paths.config_file()}).")
    except SklabError as exc:
        fail(exc)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc)


@app.command("reset")
def reset() -> None:
    """Reset configuration to defaults."""
    try:
        reset_config()
        output.success(f"Configuration reset to defaults ({paths.config_file()}).")
    except SklabError as exc:
        fail(exc)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc)


@app.command("path")
def config_path() -> None:
    """Print the config file path."""
    print(paths.config_file())
