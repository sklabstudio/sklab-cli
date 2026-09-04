"""``sklab update``: safe, ordered update planning with honest rollback reporting."""

from __future__ import annotations

import typer
from rich.table import Table

from sklab.commands.common import fail, handle_unexpected
from sklab.core import output
from sklab.core.errors import SklabError
from sklab.stack.adapters import update_module
from sklab.stack.operations import check_health, plan_update
from sklab.stack.redaction import redact_text
from sklab.stack.registry import load_registry
from sklab.stack.resolver import ResolverError
from sklab.stack.state import load_state, record_module, save_state


def register(app: typer.Typer) -> None:
    @app.command("update")
    def update(
        dry_run: bool = typer.Option(False, "--dry-run", help="Show the update plan without changing anything."),
        json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
        yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
    ) -> None:
        """Compare configured sources/versions and update modules in dependency order."""
        try:
            registry = load_registry()
            try:
                plan = plan_update(registry)
            except ResolverError as exc:
                raise SklabError(exc.code, exc.message) from exc
            if dry_run:
                if json_output:
                    output.print_json({"dry_run": True, "plan": plan})
                    return
                _render_plan(plan)
                return
            actionable = [p for p in plan if p["action"] in ("install", "update")]
            if not actionable and not json_output:
                output.success("Everything is already up to date.")
                return
            if not yes and not json_output:
                _render_plan(plan)
                typer.confirm("Proceed with update?", abort=True)
            state = load_state()
            results: list[dict[str, str]] = []
            rollback_notes: list[str] = []
            for item in plan:
                if item["action"] == "skip":
                    results.append({**item, "result": "SKIPPED"})
                    continue
                loaded = registry.modules[item["id"]]
                manifest = loaded.manifest
                install_result = update_module(manifest)
                health = check_health(manifest)
                # Rollback is only safe where the adapter supports it (local/command/git ff-only).
                # Otherwise report honestly that no automatic rollback was attempted.
                if not install_result.ok and install_result.status == "FAILED":
                    if manifest.install.type in ("local", "command", "git"):
                        rollback_notes.append(f"{item['id']}: install failed; previous marker preserved where present.")
                    else:
                        rollback_notes.append(
                            f"{item['id']}: install reported {install_result.status}; "
                            "no automatic rollback attempted (adapter does not safely support it)."
                        )
                record_module(
                    state, module_id=item["id"], version=manifest.version,
                    install_type=manifest.install.type, origin=loaded.origin,
                    manifest_fingerprint=loaded.fingerprint or manifest.fingerprint(),
                    status=health.status, health=health.status,
                )
                results.append({
                    **item,
                    "result": install_result.status,
                    "health": health.status,
                    "message": redact_text(install_result.message),
                })
            save_state(state)
            if json_output:
                output.print_json({"dry_run": False, "results": results, "rollback_notes": rollback_notes})
                return
            console = output.get_console()
            console.print("[bold]SKLab update[/bold]\n")
            table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
            table.add_column("Module", style="bold")
            table.add_column("Action")
            table.add_column("Result")
            table.add_column("Health")
            for row in results:
                table.add_row(row["id"], row["action"], row.get("result", "-"), row.get("health", "-"))
            console.print(table)
            for note in rollback_notes:
                console.print(f"  Note: {redact_text(note)}")
            console.print("\nNo force-push or destructive git reset was performed.")
        except typer.Abort:
            output.warning("Update aborted.")
            raise typer.Exit(code=1) from None
        except typer.Exit:
            raise
        except SklabError as exc:
            fail(exc, json_mode=json_output)
        except Exception as exc:  # noqa: BLE001
            handle_unexpected(exc, json_mode=json_output)


def _render_plan(plan: list[dict[str, str]]) -> None:
    console = output.get_console()
    console.print("[bold]SKLab update plan (dry run)[/bold]\n")
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Module", style="bold")
    table.add_column("Action")
    table.add_column("Reason")
    for item in plan:
        table.add_row(item["id"], item["action"], redact_text(item["reason"]))
    console.print(table)
    console.print("\nNo changes were made.")
