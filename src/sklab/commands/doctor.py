"""``sklab doctor``: read-only repository diagnostics + optional workstation stack health."""

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
        stack: bool = typer.Option(
            False, "--stack", help="Inspect the SKLab workstation stack (tools, modules, config, health)."
        ),
    ) -> None:
        """Inspect the environment and repository without changing anything.

        Default (no flags) preserves the v0.1 repository diagnostics.
        Pass --stack for workstation health (Python/Node/Git/Docker, module
        CLIs, versions, config, module health, dependency consistency,
        writable dirs). Never runs paid AI.
        """
        try:
            if stack:
                _stack_doctor(json_output)
                return
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


def _stack_doctor(json_output: bool) -> None:
    from sklab.stack.operations import stack_doctor
    from sklab.stack.redaction import redact_text
    from sklab.stack.registry import load_registry

    registry = load_registry()
    report = stack_doctor(registry)
    if json_output:
        output.print_json(report)
        return
    console = output.get_console()
    console.print("[bold]SKLab Doctor (stack)[/bold]\n")
    console.print(f"Platform: {report['platform']}  Python: {report['python']}\n")
    tools_table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    tools_table.add_column("Tool", style="bold")
    tools_table.add_column("Available")
    tools_table.add_column("Version")
    tools_raw = report.get("tools")
    tools: list[object] = tools_raw if isinstance(tools_raw, list) else []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tools_table.add_row(
            str(tool.get("tool")), str(tool.get("available")), redact_text(str(tool.get("version", "")))
        )
    console.print(tools_table)
    console.print("")
    mod_table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    mod_table.add_column("Module", style="bold")
    mod_table.add_column("Version")
    mod_table.add_column("Status")
    mod_table.add_column("Details")
    modules_raw = report.get("modules")
    modules: list[object] = modules_raw if isinstance(modules_raw, list) else []
    for item in modules:
        if not isinstance(item, dict):
            continue
        mod_table.add_row(
            str(item.get("name")), str(item.get("version")),
            output.styled_status(str(item.get("status"))),
            redact_text(str(item.get("detail", ""))),
        )
    console.print(mod_table)
    consistency_raw = report.get("dependency_consistency")
    consistency: dict[object, object] = consistency_raw if isinstance(consistency_raw, dict) else {}
    if not consistency.get("ok"):
        console.print(f"\nDependency issue: {redact_text(str(consistency.get('error')))}")
    for section in ("docker", "node", "github_auth"):
        extra = report.get(section)
        if isinstance(extra, dict):
            status = extra.get("status", extra.get("verdict", ""))
            detail = extra.get("detail", "")
            console.print(f"\n{section}: {status} - {redact_text(str(detail))}")
    path_info = report.get("path")
    if isinstance(path_info, dict):
        console.print(f"\npath: {path_info.get('bin')} on PATH: {path_info.get('on_path')}")
    resources = report.get("resources")
    if isinstance(resources, dict):
        console.print(
            f"\nresources: CPU {resources.get('cpu')} RAM {resources.get('ram_mib')} MiB "
            f"swap {resources.get('swap_mib')} MiB disk-free {resources.get('disk_free_mb')} MB "
            f"({resources.get('level')})"
        )
        warnings_raw = resources.get("warnings")
        if isinstance(warnings_raw, list):
            for warning in warnings_raw:
                console.print(f"  Note: {warning}")
    path_fix = report.get("path_fix")
    if isinstance(path_fix, list) and path_fix:
        console.print("\nPATH fix: ~/.local/bin is not on PATH. Re-run setup with --fix-path (idempotent).")
    summary_raw = report.get("summary")
    summary: dict[object, object] = summary_raw if isinstance(summary_raw, dict) else {}
    parts = [f"{k}: {v}" for k, v in sorted(summary.items(), key=lambda kv: str(kv[0]))]
    console.print(f"\nSummary: {'; '.join(parts) if parts else 'no modules'}")
    console.print("No paid AI was run.")
