"""Unit tests for Scoped Grants and temporary permissions."""

import time
from pathlib import Path
import pytest

from kaufee.config import KaufeeConfig
from kaufee.safety.grants import ScopedGrantManager, parse_duration_seconds
from kaufee.safety.policy import PolicyEngine
from kaufee.state.models import RiskLevel, ToolCall


def test_parse_duration_seconds():
    assert parse_duration_seconds("30s") == 30.0
    assert parse_duration_seconds("15m") == 900.0
    assert parse_duration_seconds("2h") == 7200.0
    assert parse_duration_seconds("1d") == 86400.0
    assert parse_duration_seconds("45") == 45.0

    with pytest.raises(ValueError):
        parse_duration_seconds("invalid_duration")


def test_scoped_grant_lifecycle():
    mgr = ScopedGrantManager()
    assert mgr.has_active_grant("workspace") is False

    # Grant 2 seconds
    grant = mgr.grant("workspace", 2.0)
    assert grant.is_active is True
    assert mgr.has_active_grant("workspace") is True
    assert len(mgr.list_active_grants()) == 1

    # Revoke
    assert mgr.revoke("workspace") is True
    assert mgr.has_active_grant("workspace") is False


def test_scoped_grant_bypasses_manual_write_approval(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="manual")
    grants = ScopedGrantManager()
    policy = PolicyEngine(cfg, grants=grants)

    write_action = ToolCall(tool_name="write_file", arguments={"path": "notes.txt", "content": "test"})

    # Without grant, manual mode requires approval
    decision = policy.validate(write_action, tmp_path)
    assert decision.requires_approval is True
    assert decision.risk_level == RiskLevel.MEDIUM

    # With active grant, approval is bypassed
    grants.grant("workspace", "15m")
    decision_granted = policy.validate(write_action, tmp_path)
    assert decision_granted.allowed is True
    assert decision_granted.requires_approval is False
    assert decision_granted.risk_level == RiskLevel.SAFE
    assert "active workspace grant" in decision_granted.reason

    # Deletions still require approval even with workspace grant
    del_action = ToolCall(tool_name="delete_file", arguments={"path": "notes.txt"})
    (tmp_path / "notes.txt").write_text("test", encoding="utf-8")
    del_decision = policy.validate(del_action, tmp_path)
    assert del_decision.requires_approval is True
    assert del_decision.risk_level == RiskLevel.HIGH
