"""Unit tests for clipboard interaction tools and redaction."""

from pathlib import Path
from unittest.mock import patch
import pytest

from kaufee.config import KaufeeConfig
from kaufee.safety.policy import PolicyEngine
from kaufee.state.models import RiskLevel, ToolCall
from kaufee.tools.clipboard import ReadClipboardTool, WriteClipboardTool


def test_clipboard_policy_evaluation(tmp_path: Path):
    cfg_manual = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="manual")
    policy_manual = PolicyEngine(cfg_manual)

    call_read = ToolCall(tool_name="read_clipboard", arguments={})
    dec_read = policy_manual.validate(call_read, tmp_path)
    assert dec_read.allowed is True
    assert dec_read.requires_approval is True
    assert dec_read.risk_level == RiskLevel.MEDIUM

    cfg_assisted = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="assisted")
    policy_assisted = PolicyEngine(cfg_assisted)
    dec_read_assisted = policy_assisted.validate(call_read, tmp_path)
    assert dec_read_assisted.allowed is True
    assert dec_read_assisted.requires_approval is False
    assert dec_read_assisted.risk_level == RiskLevel.SAFE


def test_clipboard_read_and_write_with_redaction(tmp_path: Path):
    read_tool = ReadClipboardTool()
    write_tool = WriteClipboardTool()

    # Mock clipboard operations
    fake_clipboard = [""]

    def fake_paste():
        return fake_clipboard[0]

    def fake_copy(text):
        fake_clipboard[0] = str(text)

    with patch("pyperclip.paste", side_effect=fake_paste), patch("pyperclip.copy", side_effect=fake_copy):
        # 1. Write normal text
        success_w, out_w, meta_w = write_tool.run({"content": "Hello World"}, tmp_path)
        assert success_w is True
        assert meta_w["length"] == 11
        assert fake_clipboard[0] == "Hello World"

        # 2. Read normal text
        success_r, out_r, meta_r = read_tool.run({}, tmp_path)
        assert success_r is True
        assert out_r == "Hello World"
        assert meta_r["redacted"] is False

        # 3. Read clipboard containing sensitive secret (should be redacted)
        fake_clipboard[0] = "my_token = 'sk-proj-1234567890abcdef1234567890abcdef'"
        success_sec, out_sec, meta_sec = read_tool.run({}, tmp_path)
        assert success_sec is True
        assert "[REDACTED_SECRET]" in out_sec
        assert "sk-proj-1234567890abcdef1234567890abcdef" not in out_sec
        assert meta_sec["redacted"] is True
