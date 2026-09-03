"""``sklab init``: create a new project from a starter."""

from __future__ import annotations

from pathlib import Path

import typer

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.config import load_config
from sklab.core.errors import SklabError
from sklab.core.subprocess import run_command
from sklab.starters.provider import (
    StarterProvider,
    check_destination,
    get_provider,
    require_starter,
    resolve_destination,
    validate_project_name,
)
from sklab.starters.template import process_templates


def register(app: typer.Typer) -> None:
    @app.command("init")
    def init(
        starter: str = typer.Argument(..., help="Starter to use: fullstack, api, or frontend."),
        name: str = typer.Argument(..., help="Project (directory) name, e.g. my-app."),
        source: str | None = typer.Option(None, "--source", help="Starter source: local path or owner/repo[@branch]."),
        branch: str | None = typer.Option(None, "--branch", help="Branch for remote starter sources."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen without writing files."),
        force: bool = typer.Option(False, "--force", help="Allow overlaying files into an existing directory."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Create a new project from a SKLab starter."""
        try:
            _run(starter, name, source, branch, dry_run, force, json_output)
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001 - last-resort guard with --verbose details
            handle_unexpected(exc, json_mode=json_output)


def _run(
    starter: str,
    name: str,
    source: str | None,
    branch: str | None,
    dry_run: bool,
    force: bool,
    json_output: bool,
) -> None:
    cfg = load_config()
    key = require_starter(starter)
    validate_project_name(name)
    dest = resolve_destination(name)
    check_destination(dest, force=force)
    provider = get_provider(
        source or cfg.starters_source,
        branch=branch or cfg.default_branch,
        timeout=cfg.network_timeout,
        cache_ttl=cfg.cache_ttl,
    )

    if dry_run:
        planned = _planned_files(provider, key)
        if json_output:
            output.print_json(
                {
                    "starter": key,
                    "project": name,
                    "destination": str(dest),
                    "source": provider.describe(),
                    "dry_run": True,
                    "files": planned,
                }
            )
            return
        console = output.get_console()
        console.print("[bold]SKLab CLI[/bold]\n")
        console.print(f"Starter        {key}")
        console.print(f"Project        {name}")
        console.print(f"Destination    {dest}")
        console.print(f"Source         {provider.describe()}")
        console.print("\nDry run: no files were written.\n")
        if planned:
            console.print("Files that would be created:")
            for rel in planned[:50]:
                console.print(f"  {rel}")
            if len(planned) > 50:
                console.print(f"  ... and {len(planned) - 50} more")
        else:
            console.print("Files would be fetched from the remote source on a real run.")
        return

    if not json_output:
        console = output.get_console()
        console.print("[bold]SKLab CLI[/bold]\n")
        console.print(f"Starter        {key}")
        console.print(f"Project        {name}")
        console.print(f"Destination    {dest}")
        console.print("\nFetching starter...")

    created = provider.fetch(key, dest)

    if not json_output:
        output.success("Starter downloaded")
        output.success(f"Files copied ({len(created)} files)")

    changed = process_templates(dest, name)
    if not json_output:
        output.success("Template metadata processed")

    env_created = _ensure_env_template(dest)
    if not json_output:
        if env_created:
            output.success("Environment template available (.env.example)")
        else:
            output.warning("No .env.example in starter; skipping environment template.")

    git_ok = _init_git(dest)
    if not json_output:
        if git_ok:
            output.success("Git repository initialized")
        else:
            output.warning("Git repository not initialized (git unavailable or already a repo).")
        _print_next_steps(dest, name)
    else:
        output.print_json(
            {
                "starter": key,
                "project": name,
                "destination": str(dest),
                "files": len(created),
                "templates_processed": changed,
                "git_initialized": git_ok,
            }
        )


def _planned_files(provider: StarterProvider, starter: str) -> list[str]:
    from sklab.starters.local import LocalStarterProvider

    if isinstance(provider, LocalStarterProvider):
        try:
            return provider.iter_files(starter)
        except SklabError:
            return []
    return []


def _ensure_env_template(dest: Path) -> bool:
    # Template processing already rendered .env.example; nothing to generate.
    # Never create a real .env automatically (it may hold secrets).
    return (dest / ".env.example").exists()


def _init_git(dest: Path) -> bool:
    if (dest / ".git").exists():
        return True
    result = run_command(["git", "init", str(dest)], cwd=Path.cwd(), timeout=30.0)
    return result.ok


def _print_next_steps(dest: Path, name: str) -> None:
    console = output.get_console()
    console.print("\n[bold]Project ready.[/bold]\n")
    console.print("Next:\n")
    console.print(f"  cd {name}")
    if (dest / ".env.example").exists() and not (dest / ".env").exists():
        console.print("  cp .env.example .env   (Windows: copy .env.example .env)")
    if (dest / "compose.yml").exists() or (dest / "compose.yaml").exists() or (dest / "docker-compose.yml").exists():
        console.print("  docker compose up --build")
    elif (dest / "package.json").exists():
        console.print("  npm install")
        console.print("  npm run dev")
    elif (dest / "requirements.txt").exists() or (dest / "pyproject.toml").exists():
        console.print("  python -m venv .venv")
        console.print("  pytest")
