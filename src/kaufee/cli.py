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
from kaufee.safety.principles import ResponsibleAIPrinciple, get_principle_info
from kaufee.safety.redactor import redact_sensitive_text
from kaufee.state.audit import AuditLogger
from kaufee.state.models import Plan, PolicyDecision, TaskState, TaskStatus, ToolCall, ToolResult
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

        principle_info = f"\n[bold]Responsible AI Rule:[/bold] [magenta]{decision.principle}[/magenta]" if decision.principle else ""
        console.print(
            Panel(
                f"[bold yellow]Policy Gate Required for Action:[/bold yellow] [cyan]{action.tool_name}[/cyan]\n"
                f"[bold]Risk Level:[/bold] {decision.risk_level.value}\n"
                f"[bold]Reason:[/bold] {decision.reason}{principle_info}\n"
                f"[bold]Arguments:[/bold] {json.dumps(action.arguments, indent=2)}",
                title="[red]Approval Prompt[/red]",
                border_style="yellow",
            )
        )
        return Confirm.ask("Do you authorize this action?", default=False)

    return callback


def create_plan_approval_handler(auto_approve: bool = False):
    """Factory for interactive pre-flight plan approval callback."""
    def callback(plan: Plan) -> bool:
        if auto_approve:
            return True

        steps_summary = "\n".join(
            f"  {s.step_number}. [bold green]{s.tool_name}[/bold green]: {s.description}" for s in plan.steps
        )
        console.print(
            Panel(
                f"[bold cyan]Pre-Flight Plan Approval Gate (Accountability Principle)[/bold cyan]\n\n"
                f"[bold]Proposed Execution Steps ({len(plan.steps)} total):[/bold]\n"
                f"{steps_summary}\n\n"
                f"[dim]Authorizing this plan allows planned actions to run without repetitive prompts, eliminating alert fatigue.[/dim]",
                title="[bold yellow]Pre-Flight Plan Authorization[/bold yellow]",
                border_style="yellow",
            )
        )
        return Confirm.ask("Do you authorize this entire plan to proceed autonomously?", default=True)

    return callback


def create_step_reporter():
    """Factory for interactive step callback updating terminal UI."""
    def reporter(event: str, state: TaskState, action: Optional[ToolCall] = None, result: Optional[ToolResult] = None):
        if event == "PLAN_CREATED" and state.plan:
            table = Table(title="[bold cyan]Execution Plan (Transparency Principle)[/bold cyan]", border_style="cyan")
            table.add_column("Step", style="bold yellow", width=6)
            table.add_column("Tool", style="green", width=16)
            table.add_column("Description", style="white")

            for s in state.plan.steps:
                table.add_row(str(s.step_number), s.tool_name, s.description)
            console.print(table)

        elif event == "GUARDRAIL_BLOCKED":
            console.print(
                "[bold red][GUARDRAIL BLOCKED][/bold red] Malicious directive or prompt injection intercepted "
                "(Responsible AI: Privacy & Security)."
            )

        elif event == "TOOL_EXEC_START" and action:
            arg_str = ", ".join(
                f"{k}='{v}'" if not isinstance(v, (dict, list)) else f"{k}=..."
                for k, v in action.arguments.items()
            )
            console.print(f"[bold cyan][ACT][/bold cyan]  [green]{action.tool_name}[/green]({arg_str})")

        elif event == "TOOL_EXEC_SUCCESS" and result:
            preview = result.output.strip().splitlines()[0] if result.output.strip() else "OK"
            preview = redact_sensitive_text(preview)
            if len(preview) > 90:
                preview = preview[:87] + "..."
            console.print(f"      [bold green]+[/bold green] {preview} [dim]({result.execution_time_ms:.1f}ms)[/dim]")

        elif event == "TOOL_EXEC_FAILED" and result:
            err = result.error.strip().splitlines()[0] if result.error else "Failed"
            err = redact_sensitive_text(err)
            console.print(f"      [bold red]x Error:[/bold red] {err}")

        elif event == "ACTION_BLOCKED" and action:
            console.print(f"[bold red][BLOCKED][/bold red] Action [cyan]{action.tool_name}[/cyan] was rejected by security policy.")

    return reporter


@app.command()
def run(
    goal: str = typer.Argument(..., help="The plain-English task goal to execute."),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider ('ollama', 'remote', 'mock', 'hybrid')."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Autonomy mode: 'manual', 'assisted', or 'autonomous'."),
    approval_mode: Optional[str] = typer.Option(None, "--approval-mode", help="Approval scope: 'plan' (approve full plan upfront) or 'step'."),
    runner: Optional[str] = typer.Option(None, "--runner", help="Execution runner: 'auto', 'subprocess', or 'docker'."),
    grant_workspace: Optional[str] = typer.Option(None, "--grant-workspace", help="Temporary workspace write/edit authorization (e.g. '15m', '1h')."),
    timeout: int = typer.Option(300, "--timeout", "-t", help="LLM request timeout in seconds (default 300)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Automatically approve risky actions."),
) -> None:
    """Execute a task goal in the workspace."""
    cfg = KaufeeConfig.load(
        workspace=workspace,
        provider=provider,
        model=model,
        autonomy_mode=mode,
        approval_mode=approval_mode,
    )
    if runner:
        cfg.runner_type = runner.lower().strip()

    grant_info = ""
    if grant_workspace:
        grant_info = f"\n[bold]Scoped Grant:[/bold] [cyan]workspace ({grant_workspace})[/cyan]"

    console.print(
        Panel(
            f"[bold]Goal:[/bold] {goal}\n"
            f"[bold]Workspace:[/bold] {cfg.workspace_root}\n"
            f"[bold]Autonomy Mode:[/bold] {cfg.autonomy_mode.upper()} | [bold]Approval Gate:[/bold] {cfg.approval_mode.upper()}\n"
            f"[bold]LLM Provider:[/bold] {cfg.llm_provider} | [bold]Runner:[/bold] {cfg.runner_type.upper()}{grant_info}",
            title=f"[bold green]Kaufee-Home v{__version__}[/bold green]",
            border_style="green",
        )
    )

    controller = AgentController(config=cfg, llm_timeout=timeout)
    if grant_workspace:
        controller.grants.grant("workspace", grant_workspace)
    approval_cb = create_approval_handler(auto_approve=yes)
    plan_approval_cb = create_plan_approval_handler(auto_approve=yes)
    step_cb = create_step_reporter()

    final_state = controller.run_task(
        goal=goal,
        approval_callback=approval_cb,
        plan_approval_callback=plan_approval_cb,
        step_callback=step_cb,
    )

    # Verification inspection
    if final_state.verification_result:
        v_res = final_state.verification_result
        console.print("\n[bold cyan][CHECK][/bold cyan] Inspecting verification postconditions (Reliability Principle):")
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
                        redact_sensitive_text(out),
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
    mode: Optional[str] = typer.Option(None, "--mode", help="Autonomy mode: 'manual', 'assisted', or 'autonomous'."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve risky operations."),
) -> None:
    """Start an interactive interactive REPL session."""
    cfg = KaufeeConfig.load(workspace=workspace, provider=provider, autonomy_mode=mode)
    controller = AgentController(config=cfg)

    console.print(
        Panel(
            f"[bold green]Kaufee-Home Interactive Shell[/bold green] (v{__version__})\n"
            f"Workspace: {cfg.workspace_root}\n"
            f"Autonomy Mode: {cfg.autonomy_mode.upper()}\n"
            f"Provider: {cfg.llm_provider}\n"
            "Type your task in plain English. Special commands: [cyan]help[/cyan], [cyan]principles[/cyan], [cyan]config[/cyan], [cyan]undo[/cyan], [cyan]exit[/cyan]",
            border_style="cyan",
        )
    )

    approval_cb = create_approval_handler(auto_approve=yes)
    plan_approval_cb = create_plan_approval_handler(auto_approve=yes)
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
                console.print("Commands:\n  dashboard  - Open in-terminal TUI dashboard\n  principles - Show Responsible AI mapping\n  config     - Show active settings\n  undo <file>- Restore file backup\n  exit       - Exit shell")
                continue
            elif cmd_lower in ("dashboard", "tui"):
                from kaufee.ui.dashboard import run_dashboard
                run_dashboard(cfg)
                continue
            elif cmd_lower in ("principles", "rai", "/principles"):
                show_principles()
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
                plan_approval_callback=plan_approval_cb,
                step_callback=step_cb,
            )
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break


@app.command("principles")
def show_principles() -> None:
    """Display the 6 Responsible AI Principles and how Kaufee-Home enforces each one."""
    table = Table(
        title="[bold green]Principles of Responsible AI in Kaufee-Home[/bold green]",
        border_style="cyan",
    )
    table.add_column("Principle", style="bold yellow", width=22)
    table.add_column("Challenge or Risk", style="bold red", width=26)
    table.add_column("Example", style="white", width=34)
    table.add_column("Kaufee-Home Mitigation", style="green", width=42)

    for p in ResponsibleAIPrinciple:
        info = get_principle_info(p)
        table.add_row(
            info["title"],
            info["challenge_or_risk"],
            info["example"],
            info["agentic_mitigation"],
        )
    console.print(table)


@app.command("dashboard")
def dashboard_command(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Launch the interactive in-terminal Textual TUI dashboard."""
    from kaufee.ui.dashboard import run_dashboard
    cfg = KaufeeConfig.load(workspace=workspace)
    run_dashboard(cfg)


@app.command("tui")
def tui_command(
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="Workspace root directory."),
) -> None:
    """Launch the interactive in-terminal Textual TUI dashboard (alias for dashboard)."""
    dashboard_command(workspace=workspace)


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
    table.add_row("Autonomy Mode", cfg.autonomy_mode)
    table.add_row("Approval Gate Scope", cfg.approval_mode)
    table.add_row("LLM Provider", cfg.llm_provider)
    table.add_row("Ollama Base URL", cfg.ollama_base_url)
    table.add_row("Ollama Model", cfg.ollama_model)
    table.add_row("Remote API Base URL", cfg.remote_api_base_url)
    table.add_row("Remote Model", cfg.remote_model)
    table.add_row("Max Steps", str(cfg.max_steps))
    table.add_row("Max Repairs", str(cfg.max_repairs))
    table.add_row("Step Timeout (s)", str(cfg.step_timeout))
    table.add_row("Require Approval For Delete", str(cfg.require_approval_for_delete))
    table.add_row("Require Approval For Python", str(cfg.require_approval_for_python))
    table.add_row("Allow Arbitrary Shell", str(cfg.allow_arbitrary_shell))
    table.add_row("Prompt Injection Guard", str(cfg.enable_prompt_injection_guard))
    table.add_row("Sensitive Data Redaction", str(cfg.enable_sensitive_data_redaction))
    table.add_row("Circuit Breaker Repetition Threshold", str(cfg.circuit_breaker_threshold))
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
            p_badge = f"[magenta][{r.principle}][/magenta] " if r.principle else ""
            console.print(f"[dim]{r.timestamp}[/dim] [bold yellow]{r.event_type}[/bold yellow] {p_badge}{json.dumps(r.details)}")
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
