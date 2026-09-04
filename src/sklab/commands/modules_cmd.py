"""``sklab modules`` and ``sklab module``: registry inspection + local extension."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.stack import home as stack_home
from sklab.stack.adapters import plan_install
from sklab.stack.manifest import ModuleManifest
from sklab.stack.operations import check_health
from sklab.stack.redaction import redact_text
from sklab.stack.registry import add_manifest_file, load_registry
from sklab.stack.state import load_state, record_module, save_state


def _list_modules(json_output: bool) -> None:
    try:
        registry = load_registry()
        rows = []
        for module_id in sorted(registry.modules.keys()):
            loaded = registry.modules[module_id]
            rows.append(loaded.to_summary())
        if json_output:
            output.print_json({"modules": rows, "errors": registry.errors})
            return
        console = output.get_console()
        console.print("[bold]SKLab modules[/bold]\n")
        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("ID", style="bold")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Visibility")
        table.add_column("Origin")
        for module_id in sorted(registry.modules.keys()):
            loaded = registry.modules[module_id]
            table.add_row(
                loaded.manifest.id, loaded.manifest.name, loaded.manifest.version,
                loaded.manifest.visibility, loaded.origin,
            )
        console.print(table)
        if registry.errors:
            console.print("\n[bold]Registry warnings:[/bold]")
            for err in registry.errors:
                console.print(f"  {redact_text(str(err))}")
    except SklabError as exc:
        fail(exc, json_mode=json_output)
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc, json_mode=json_output)


def register_modules(app: typer.Typer) -> None:
    modules_app = typer.Typer(
        help="List modules or register a local manifest.", no_args_is_help=False,
        invoke_without_command=True,
    )

    @modules_app.callback()
    def _modules_callback(
        ctx: typer.Context,
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        if ctx.invoked_subcommand is None:
            _list_modules(json_output)

    @modules_app.command("add-manifest")
    def modules_add_manifest(
        path: Path = typer.Argument(..., help="Local manifest file to register."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Register an optional local/private manifest (stays local, never uploaded)."""
        _add_manifest(path, json_output)

    app.add_typer(modules_app, name="modules")

    @app.command("modules-add-manifest")
    def modules_add_manifest_flat(
        path: Path = typer.Argument(..., help="Local manifest file to register."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Register an optional local/private manifest (flat alias; stays local)."""
        _add_manifest(path, json_output)


def register_module_group(app: typer.Typer) -> None:
    module_app = typer.Typer(help="Per-module install/remove/doctor.", no_args_is_help=True)
    app.add_typer(module_app, name="module")

    @module_app.command("install")
    def module_install(
        module_id: str = typer.Argument(..., help="Module id."),
        dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan without installing."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Install a single module (idempotent)."""
        try:
            from sklab.stack.adapters import install_module

            registry = load_registry()
            loaded = registry.modules.get(module_id)
            if loaded is None:
                raise SklabError("RESOURCE_NOT_FOUND", f"Unknown module: {module_id}.",
                                 remediation="Run 'sklab modules' to list configured modules.")
            manifest = loaded.manifest
            if dry_run:
                preview = plan_install(manifest)
                if json_output:
                    output.print_json({"id": module_id, "dry_run": True, "plan": preview})
                    return
                console = output.get_console()
                console.print(f"[bold]Install plan for {module_id}[/bold]\n")
                for step in preview:
                    console.print(f"  {' '.join(redact_text(a) for a in step)}")
                console.print("\nNo changes were made.")
                return
            result = install_module(manifest, dry_run=False)
            health = check_health(manifest)
            if not dry_run:
                state = load_state()
                record_module(
                    state, module_id=module_id, version=manifest.version,
                    install_type=manifest.install.type, origin=loaded.origin,
                    manifest_fingerprint=loaded.fingerprint or manifest.fingerprint(),
                    status=health.status, health=health.status,
                )
                save_state(state)
            if json_output:
                output.print_json({
                    "id": module_id,
                    "ok": result.ok,
                    "install_status": result.status,
                    "message": redact_text(result.message),
                    "health": health.status,
                    "health_detail": redact_text(health.detail),
                })
                if not result.ok:
                    raise typer.Exit(code=1)
                return
            console = output.get_console()
            console.print(f"Install: {result.status} — {redact_text(result.message)}")
            console.print(f"Health: {health.status} — {redact_text(health.detail)}")
            if not result.ok:
                raise typer.Exit(code=1)
        except typer.Exit:
            raise
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)

    @module_app.command("remove")
    def module_remove(
        module_id: str = typer.Argument(..., help="Module id."),
        yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Forget the install record and remove the local install marker (never deletes user repos)."""
        try:
            registry = load_registry()
            if module_id not in registry.modules:
                raise SklabError("RESOURCE_NOT_FOUND", f"Unknown module: {module_id}.")
            if not yes and not json_output:
                typer.confirm(f"Remove install record for '{module_id}'?", abort=True)
            marker = stack_home.install_root() / module_id / ".sklab-installed"
            removed_marker = False
            if marker.exists():
                marker.unlink(missing_ok=True)
                removed_marker = True
            state = load_state()
            forgotten = state.modules.pop(module_id, None) is not None
            save_state(state)
            if json_output:
                output.print_json({"id": module_id, "forgotten": forgotten, "removed_marker": removed_marker})
                return
            output.success(f"Removed '{module_id}' (record forgotten: {forgotten}).")
        except typer.Abort:
            output.warning("Remove aborted.")
            raise typer.Exit(code=1) from None
        except typer.Exit:
            raise
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)

    @module_app.command("doctor")
    def module_doctor(
        module_id: str = typer.Argument(..., help="Module id."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Run the zero-cost health check for a single module."""
        try:
            registry = load_registry()
            loaded = registry.modules.get(module_id)
            if loaded is None:
                raise SklabError("RESOURCE_NOT_FOUND", f"Unknown module: {module_id}.")
            result = check_health(loaded.manifest)
            if json_output:
                output.print_json({
                    "id": result.id, "name": result.name, "version": result.version,
                    "status": result.status, "detail": redact_text(result.detail),
                })
                return
            console = output.get_console()
            console.print(f"[bold]{result.name} ({result.id})[/bold]: {output.styled_status(result.status)}")
            console.print(redact_text(result.detail))
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)

    @module_app.command("add-manifest")
    def module_add_manifest(
        path: Path = typer.Argument(..., help="Local manifest file to register."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    ) -> None:
        """Alias for registering a local manifest (stays local)."""
        _add_manifest(path, json_output)


def _add_manifest(path: Path, json_output: bool) -> None:
    try:
        loaded = add_manifest_file(Path(path))
        manifest: ModuleManifest = loaded.manifest
        if json_output:
            output.print_json({"id": manifest.id, "path": loaded.path, "visibility": manifest.visibility})
            return
        output.success(f"Registered '{manifest.id}' ({manifest.visibility}) from {loaded.path}.")
    except ValueError as exc:
        raise SklabError("CONFIG_ERROR", redact_text(str(exc))) from exc
    except SklabError:
        raise
    except Exception as exc:  # noqa: BLE001
        handle_unexpected(exc, json_mode=json_output)
