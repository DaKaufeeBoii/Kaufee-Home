"""Unit test verifying that Textual dashboard loads properly."""

from pathlib import Path
from kaufee.config import KaufeeConfig
from kaufee.ui.dashboard import KaufeeDashboardApp


def test_dashboard_app_initialization(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path)
    app = KaufeeDashboardApp(config=cfg)
    assert app.config == cfg
    assert app.audit_dir == cfg.audit_dir
