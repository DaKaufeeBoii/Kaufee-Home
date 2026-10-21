"""Command-line interface for Kaufee-Home using Typer and Rich."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from kaufee import __version__
from kaufee.agent.controller import AgentController
from kaufee.config import KaufeeConfig
from kaufee.state.audit import AuditLogger
from kaufee.state.models import PolicyDecision, TaskState, TaskStatus, ToolCall, ToolResult
from kaufee.tools.workspace import WorkspaceManager


app = typer.Typer(
    name="kaufee",
    help="Kaufee-Home: Lightweight, local-first, AI-powered CLI agent for verifiable coding and workspace tasks.",
    no_args_is_help=False,
)
console = Console(safe_box=True)


def create_approval_handler(auto_approve: bool = False):
    """Factory for interactive approval prompt callback."""
    def callback(action: ToolCall, decision: PolicyDecision) -> bool:
        if auto_approve:
            console.print(f"[yellow]Auto-approving risky action: {action.tool_name} ({decision.reason})[/yellow]")
            return True

        console.print(
            Panel(
                f"[bold yellow]Policy Gate Required for Action:[/bold yellow] [cyan]{action.tool_name}[/cyan]\n"
                f"[bold]Risk Level:[/bold] {decision.risk_level.value}\n"
                f"[bold]Reason:[/bold] {decision.reason}\n"
                f"[bold]Arguments:[/bold] {json.dumps(action.arguments, indent=2)}",
                title="[red]Approval Prompt[/red]",
                border_style="yellow",
            )
        )
        return Confirm.ask("Do you authorize this action?", default=False)

    return callback


def create_step_reporter():
    """Factory for interactive step callback updating terminal UI."""
    def reporter(event: str, state: TaskState, action: Optional[ToolCall] = None, result: Optional[ToolResult] = None):
        if event == "PLAN_CREATED" and state.plan:
            table = Table(title="[bold cyan]Execution Plan[/bold cyan]", border_style="cyan")
            table.add_column("Step", style="bold yellow", width=6)
            table.add_column("Tool", style="green", width=16)
            table.add_column("Description", style="white")

            for s in state.plan.steps:
                table.add_row(str(s.step_number), s.tool_name, s.description)
            console.print(table)

        elif event == "TOOL_EXEC_START" and action:
            arg_str = ", ".join(f"{k}='{v}'" if not isinstance(v, (dict, list)) else f"{k}=..." for k, v in action.arguments.items())
            console.print(f"[bold cyan][ACT][/bold cyan]  [green]{action.tool_name}[/green]({arg_str})")

        elif event == "TOOL_EXEC_SUCCESS" and result:
            preview = result.output.strip().splitlines()[0] if result.output.strip() else "OK"
            if len(preview) > 90:
                preview = preview[:87] + "..."
            console.print(f"      [bold green]+[/bold green] {preview} [dim]({result.execution_time_ms:.1f}ms)[/dim]")

        elif event == "TOOL_EXEC_FAILED" and result:
            err = result.error.strip().splitlines()[0] if result.error else "Failed"
            console.print(f"      [bold red]x Error:[/bold red] {err}")

        elif event == "ACTION_BLOCKED" and action:
            console.print(f"[bold red][BLOCKED][/bold red] Action [cyan]{action.tool_name}[/cyan] was rejected by security policy.")

    return reporter


@app.command()
def run(
    goal: str = typer.Argument(..., help="The plain-English task goal to execute."),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider ('ollama', 'remote', 'mock')."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name."),
    timeout: int = typer.Option(300, "--timeout", "-t", help="LLM request timeout in seconds (default 300, increase for slow CPU inference)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Automatically approve risky actions."),
) -> None:
    """Execute a task goal in the workspace."""
    cfg = KaufeeConfig.load(workspace=workspace, provider=provider, model=model)

    console.print(
        Panel(
            f"[bold]Goal:[/bold] {goal}\n"
            f"[bold]Workspace:[/bold] {cfg.workspace_root}\n"
            f"[bold]LLM Provider:[/bold] {cfg.llm_provider} ({cfg.ollama_model if cfg.llm_provider == 'ollama' else cfg.remote_model})",
            title=f"[bold green]Kaufee-Home v{__version__}[/bold green]",
            border_style="green",
        )
    )

    controller = AgentController(config=cfg, llm_timeout=timeout)
    approval_cb = create_approval_handler(auto_approve=yes)
    step_cb = create_step_reporter()

    final_state = controller.run_task(
        goal=goal,
        approval_callback=approval_cb,
        step_callback=step_cb,
    )

    # Verification inspection
    if final_state.verification_result:
        v_res = final_state.verification_result
        console.print("\n[bold cyan][CHECK][/bold cyan] Inspecting verification postconditions:")
        for check in v_res.checks:
            mark = "[bold green][+][/bold green]" if check.passed else "[bold red][x][/bold red]"
            console.print(f"  {mark} {check.name}: {check.details}")

    # Result Banner
    if final_state.status == TaskStatus.COMPLETED:
        # For informational or query tasks, display the relevant output prominently
        for entry in final_state.history:
            action = entry.get("action", {})
            result = entry.get("result", {})
            tname = action.get("tool_name")
            out = (result.get("output") or "").strip()
            if out and tname in ("list_files", "read_file", "python_runner"):
                console.print(
                    Panel(
                        out,
                        title=f"[bold cyan]{tname} Output[/bold cyan]",
                        border_style="cyan",
                    )
                )

        console.print(
            Panel(
                f"[bold green]Task Completed Successfully![/bold green]\n"
                f"Tool calls: {final_state.tool_calls_succeeded}/{final_state.tool_calls_attempted} succeeded | "
                f"Repairs: {final_state.repair_count}/{final_state.max_repairs}\n"
                f"Audit ID: [dim]{final_state.task_id}[/dim]",
                title="[bold green]RESULT: SUCCESS[/bold green]",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]Task Did Not Complete Successfully[/bold red]\n"
                f"Status: {final_state.status.value}\n"
                f"Reason: {final_state.error_message or 'Unmet postconditions'}\n"
                f"Audit ID: [dim]{final_state.task_id}[/dim]",
                title="[bold red]RESULT: FAILED[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)


@app.command()
def interactive(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider ('ollama', 'remote', 'mock')."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve risky operations."),
) -> None:
    """Start an interactive interactive REPL session."""
    cfg = KaufeeConfig.load(workspace=workspace, provider=provider)
    controller = AgentController(config=cfg)

    console.print(
        Panel(
            f"[bold green]Kaufee-Home Interactive Shell[/bold green] (v{__version__})\n"
            f"Workspace: {cfg.workspace_root}\n"
            f"Provider: {cfg.llm_provider}\n"
            "Type your task in plain English. Special commands: [cyan]help[/cyan], [cyan]config[/cyan], [cyan]undo[/cyan], [cyan]exit[/cyan]",
            border_style="cyan",
        )
    )

    approval_cb = create_approval_handler(auto_approve=yes)
    step_cb = create_step_reporter()

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]kaufee>[/bold green]").strip()
            if not user_input:
                continue

            cmd_lower = user_input.lower()
            if cmd_lower in ("exit", "quit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break
            elif cmd_lower == "help":
                console.print("Commands:\n  config - Show active settings\n  undo <file> - Restore file backup\n  exit - Exit shell")
                continue
            elif cmd_lower == "config":
                show_config(cfg)
                continue
            elif cmd_lower.startswith("undo"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    ws_mgr = WorkspaceManager(cfg.workspace_root)
                    ok, msg = ws_mgr.restore_latest_backup(parts[1])
                    console.print(f"[{'green' if ok else 'red'}]{msg}[/]")
                else:
                    console.print("[red]Usage: undo <path>[/red]")
                continue

            # Run task
            controller.run_task(
                goal=user_input,
                approval_callback=approval_cb,
                step_callback=step_cb,
            )
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break


@app.command("config")
def config_command(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Display active configuration settings and limits."""
    cfg = KaufeeConfig.load(workspace=workspace)
    show_config(cfg)


def show_config(cfg: KaufeeConfig) -> None:
    table = Table(title="[bold cyan]Kaufee-Home Configuration[/bold cyan]", border_style="cyan")
    table.add_column("Parameter", style="bold white")
    table.add_column("Value", style="green")

    table.add_row("Workspace Root", str(cfg.workspace_root))
    table.add_row("LLM Provider", cfg.llm_provider)
    table.add_row("Ollama Base URL", cfg.ollama_base_url)
    table.add_row("Ollama Model", cfg.ollama_model)
    table.add_row("Remote API Base URL", cfg.remote_api_base_url)
    table.add_row("Remote Model", cfg.remote_model)
    table.add_row("Max Steps", str(cfg.max_steps))
    table.add_row("Max Repairs", str(cfg.max_repairs))
    table.add_row("Step Timeout (s)", str(cfg.step_timeout))
    table.add_row("Require Approval For Delete", str(cfg.require_approval_for_delete))
    table.add_row("Allow Arbitrary Shell", str(cfg.allow_arbitrary_shell))
    table.add_row("Audit Log Directory", str(cfg.audit_dir))
    table.add_row("Backup Directory", str(cfg.backup_dir))

    console.print(table)


@app.command()
def audit(
    task_id: Optional[str] = typer.Argument(None, help="Specific task ID to inspect."),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root."),
) -> None:
    """View task audit logs and history."""
    cfg = KaufeeConfig.load(workspace=workspace)
    audit_dir = cfg.audit_dir

    if not audit_dir.exists():
        console.print("[yellow]No audit logs found.[/yellow]")
        return

    if task_id:
        log_files = list(audit_dir.glob(f"*{task_id}*.audit.json"))
        if not log_files:
            console.print(f"[red]No audit log found matching '{task_id}'.[/red]")
            return
        records = AuditLogger.load_task_records(log_files[0])
        console.print(f"[bold cyan]Audit Log for Task {task_id}:[/bold cyan] ({len(records)} events)")
        for r in records:
            console.print(f"[dim]{r.timestamp}[/dim] [bold yellow]{r.event_type}[/bold yellow] {json.dumps(r.details)}")
    else:
        table = Table(title="Recent Task Audits", border_style="cyan")
        table.add_column("Task ID", style="bold green")
        table.add_column("File", style="dim")

        for f in sorted(audit_dir.glob("*.audit.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:15]:
            table.add_row(f.stem.replace(".audit", ""), f.name)
        console.print(table)


@app.command()
def undo(
    path: str = typer.Argument(..., help="Relative path of file to revert from backup."),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root."),
) -> None:
    """Revert a file to its latest backup snapshot."""
    cfg = KaufeeConfig.load(workspace=workspace)
    ws_mgr = WorkspaceManager(cfg.workspace_root)
    ok, msg = ws_mgr.restore_latest_backup(path)
    if ok:
        console.print(f"[bold green][+][/bold green] {msg}")
    else:
        console.print(f"[bold red][x][/bold red] {msg}")
        raise typer.Exit(code=1)


@app.command()
def benchmark(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root for benchmark."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed step logs."),
) -> None:
    """Run the 20-task evaluation benchmark suite and report metrics."""
    from kaufee.evaluation.benchmark import run_full_benchmark
    run_full_benchmark(workspace_override=workspace, verbose=verbose)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show Kaufee-Home version and exit."),
) -> None:
    if version:
        console.print(f"Kaufee-Home version [bold green]{__version__}[/bold green]")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        interactive()


if __name__ == "__main__":
    app()
