"""Unit tests for desktop system tools (app launch, processes, notifications)."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from kaufee.config import KaufeeConfig
from kaufee.safety.policy import PolicyEngine
from kaufee.state.models import RiskLevel, ToolCall
from kaufee.tools.system import DesktopNotificationTool, LaunchApplicationTool, ListProcessesTool


def test_launch_app_security_policy(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="assisted")
    policy = PolicyEngine(cfg)

    # 1. Dangerous shell binary is strictly blocked
    dangerous_call = ToolCall(tool_name="launch_application", arguments={"app_name": "cmd.exe"})
    dec_danger = policy.validate(dangerous_call, tmp_path)
    assert dec_danger.allowed is False
    assert dec_danger.risk_level == RiskLevel.CRITICAL
    assert "blocked by security policy" in dec_danger.reason

    # 2. Benign application requires approval in assisted mode
    safe_call = ToolCall(tool_name="launch_application", arguments={"app_name": "notepad"})
    dec_safe = policy.validate(safe_call, tmp_path)
    assert dec_safe.allowed is True
    assert dec_safe.requires_approval is True
    assert dec_safe.risk_level == RiskLevel.HIGH


def test_launch_app_execution_mocked(tmp_path: Path):
    tool = LaunchApplicationTool()

    # Blocked binary
    success, out, _ = tool.run({"app_name": "powershell.exe"}, tmp_path)
    assert success is False
    assert "blocked by security policy" in out

    # Non-existent binary
    success2, out2, _ = tool.run({"app_name": "non_existent_app_12345"}, tmp_path)
    assert success2 is False
    assert "was not found on system PATH" in out2

    # Successful launch mocked
    with patch("shutil.which", return_value="notepad.exe"):
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 9999
            mock_popen.return_value = mock_proc

            success3, out3, meta = tool.run({"app_name": "notepad"}, tmp_path)
            assert success3 is True
            assert "9999" in out3
            assert meta["pid"] == 9999


def test_list_processes_tool(tmp_path: Path):
    tool = ListProcessesTool()
    success, output, meta = tool.run({"limit": 5}, tmp_path)
    assert success is True
    assert "PID" in output
    assert "MEM %" in output
    assert meta["count"] <= 5


def test_desktop_notification_tool_mocked(tmp_path: Path):
    tool = DesktopNotificationTool()

    with patch("subprocess.Popen") as mock_popen:
        success, output, meta = tool.run(
            {"title": "Test Title", "message": "Test notification message"},
            tmp_path,
        )
        assert success is True
        assert "Test notification message" in output
        assert mock_popen.called
