"""UI module for Kaufee-Home including in-terminal dashboard and web UI."""
from kaufee.ui.dashboard import run_dashboard
from kaufee.ui.web import LocalDashboardServer

__all__ = ["run_dashboard", "LocalDashboardServer"]
