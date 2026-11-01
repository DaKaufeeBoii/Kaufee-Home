"""In-terminal Textual TUI dashboard for Kaufee-Home."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    Static,
)

from kaufee.config import KaufeeConfig
from kaufee.safety.principles import ResponsibleAIPrinciple, get_principle_info
from kaufee.state.audit import AuditLogger


class TaskDetailsWidget(Static):
    """Displays formatted details of a selected task audit."""

    def update_task(self, task_file: Path) -> None:
        if not task_file.is_file():
            self.update("No task selected.")
            return

        records = AuditLogger.load_task_records(task_file)
        if not records:
            self.update("Empty audit log.")
            return

        lines = [f"[bold green]Task File:[/bold green] {task_file.name}", f"[bold cyan]Total Events:[/bold cyan] {len(records)}", ""]

        for idx, r in enumerate(records, start=1):
            p_badge = f"[magenta][{r.principle}][/magenta] " if r.principle else ""
            lines.append(f"{idx}. [dim]{r.timestamp[11:19]}[/dim] [bold yellow]{r.event_type}[/bold yellow] {p_badge}")
            if "goal" in r.details:
                lines.append(f"   [bold]Goal:[/bold] {r.details['goal']}")
            elif "action" in r.details:
                action = r.details.get("action", {})
                lines.append(f"   [green]{action.get('tool_name')}[/green]({json.dumps(action.get('arguments', {}))})")
            elif "result" in r.details:
                res = r.details.get("result", {})
                status_color = "green" if res.get("success") else "red"
                lines.append(f"   [{status_color}]Result: {res.get('output') or res.get('error')}[/{status_color}]")
            lines.append("")

        self.update("\n".join(lines))


class KaufeeDashboardApp(App):
    """Full-featured In-Terminal TUI Dashboard for Kaufee-Home."""

    CSS = """
    Screen {
        background: $surface;
    }
    #sidebar {
        width: 35%;
        border-right: solid $primary;
        padding: 1;
    }
    #main-content {
        width: 65%;
        padding: 1;
    }
    .box-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit Dashboard"),
        ("r", "refresh_tasks", "Refresh Tasks"),
    ]

    def __init__(self, config: KaufeeConfig):
        super().__init__()
        self.config = config
        self.audit_dir = config.audit_dir

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("Recent Tasks & Audits", classes="box-title")
                yield DataTable(id="tasks-table")
            with VerticalScroll(id="main-content"):
                yield Label("Task Execution & Event Stream", classes="box-title")
                yield TaskDetailsWidget(id="task-details")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"Kaufee-Home In-Terminal Dashboard ({self.config.autonomy_mode.upper()} Mode)"
        table = self.query_one("#tasks-table", DataTable)
        table.add_columns("Time", "Task ID", "Events")
        table.cursor_type = "row"
        self.action_refresh_tasks()

    def action_refresh_tasks(self) -> None:
        table = self.query_one("#tasks-table", DataTable)
        table.clear()

        if not self.audit_dir.exists():
            return

        log_files = sorted(self.audit_dir.glob("*.audit.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:25]
        for f in log_files:
            task_id = f.stem.replace(".audit", "")
            records = AuditLogger.load_task_records(f)
            time_str = records[0].timestamp[11:19] if records else "--:--:--"
            table.add_row(time_str, task_id[:16], str(len(records)), key=str(f))

        if log_files:
            first_file = log_files[0]
            details = self.query_one("#task-details", TaskDetailsWidget)
            details.update_task(first_file)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        file_path = Path(str(event.row_key.value))
        details = self.query_one("#task-details", TaskDetailsWidget)
        details.update_task(file_path)


def run_dashboard(config: Optional[KaufeeConfig] = None) -> None:
    """Launch the interactive in-terminal dashboard."""
    cfg = config or KaufeeConfig.load()
    app = KaufeeDashboardApp(config=cfg)
    app.run()
