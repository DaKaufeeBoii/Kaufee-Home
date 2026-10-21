"""Safety tests for approval gates on destructive or sensitive operations."""

from pathlib import Path
from kaufee.config import KaufeeConfig
from kaufee.safety.policy import PolicyEngine
from kaufee.state.models import RiskLevel, ToolCall


def test_delete_requires_approval_by_default(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path, require_approval_for_delete=True)
    policy = PolicyEngine(cfg)

    # Create dummy file inside workspace
    dummy = tmp_path / "target.txt"
    dummy.write_text("content", encoding="utf-8")

    action = ToolCall(tool_name="delete_file", arguments={"path": "target.txt"})
    decision = policy.validate(action, tmp_path)

    assert decision.allowed is True
    assert decision.requires_approval is True
    assert decision.risk_level == RiskLevel.HIGH


def test_arbitrary_shell_disabled_by_default(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path, allow_arbitrary_shell=False)
    policy = PolicyEngine(cfg)

    action = ToolCall(tool_name="run_shell", arguments={"cmd": "whoami"})
    decision = policy.validate(action, tmp_path)

    assert decision.allowed is False
    assert decision.requires_approval is False
    assert "disabled by default" in decision.reason.lower()


def test_package_install_requires_approval(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path, require_approval_for_install=True)
    policy = PolicyEngine(cfg)

    action = ToolCall(tool_name="install_package", arguments={"package": "requests"})
    decision = policy.validate(action, tmp_path)

    assert decision.allowed is True
    assert decision.requires_approval is True
