"""Unit tests for standalone local web dashboard server."""

import time
from pathlib import Path
import httpx
import pytest

from kaufee.config import KaufeeConfig
from kaufee.ui.web import LocalDashboardServer


def test_web_dashboard_server(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path)
    server = LocalDashboardServer(cfg, host="127.0.0.1", port=18765)

    try:
        server.start(open_browser=False)
        time.sleep(0.5)

        base_url = "http://127.0.0.1:18765"
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
            # 1. Main HTML dashboard
            resp_html = client.get("/")
            assert resp_html.status_code == 200
            assert "text/html" in resp_html.headers.get("content-type", "")
            assert "Kaufee-Home Dashboard" in resp_html.text

            # 2. Status API
            resp_status = client.get("/api/status")
            assert resp_status.status_code == 200
            status_data = resp_status.json()
            assert "version" in status_data
            assert "workspace_root" in status_data
            assert status_data["autonomy_mode"] == "assisted"

            # 3. Principles API
            resp_principles = client.get("/api/principles")
            assert resp_principles.status_code == 200
            principles_data = resp_principles.json()
            assert len(principles_data) == 6
            principle_names = [p["principle"] for p in principles_data]
            assert "Fairness" in principle_names
            assert "Transparency" in principle_names

            # 4. Audits API
            resp_audits = client.get("/api/audits")
            assert resp_audits.status_code == 200
            assert isinstance(resp_audits.json(), list)

    finally:
        server.stop()
