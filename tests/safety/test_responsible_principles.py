"""Comprehensive tests verifying adherence to all 6 Responsible AI Principles.

Directly validates:
1. Fairness
2. Reliability & Safety
3. Privacy & Security
4. Inclusiveness
5. Transparency
6. Accountability
"""

from pathlib import Path
from kaufee.config import KaufeeConfig
from kaufee.safety.principles import ResponsibleAIPrinciple, get_principle_info
from kaufee.safety.policy import PolicyEngine
from kaufee.state.audit import AuditLogger
from kaufee.state.models import RiskLevel, ToolCall, ToolResult


# 1. Fairness
def test_fairness_principle_metadata_and_validation():
    info = get_principle_info(ResponsibleAIPrinciple.FAIRNESS)
    assert info["title"] == "Fairness"
    assert "bias" in info["challenge_or_risk"].lower()
    assert "PolicyEngine" in info["enforcing_components"]


# 2. Reliability & Safety
def test_reliability_safety_enforces_bounds_and_policies(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path, max_steps=5, max_repairs=2)
    policy = PolicyEngine(cfg)

    # Shell is blocked by default under Reliability & Safety
    action = ToolCall(tool_name="run_shell", arguments={"cmd": "dir"})
    decision = policy.validate(action, tmp_path)
    assert decision.allowed is False
    assert decision.principle == ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY.value


# 3. Privacy & Security
def test_privacy_security_redacts_credentials_in_audit_logs(tmp_path: Path):
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(audit_dir=audit_dir, task_id="test-privacy-01", enable_redaction=True)

    logger.log(
        "TOOL_EXEC",
        {"api_token": "Bearer abcdef1234567890abcdef1234567890", "password": "supersecretpassword!"},
        principle=ResponsibleAIPrinciple.PRIVACY_AND_SECURITY.value,
    )

    records = AuditLogger.load_task_records(logger.log_file)
    assert len(records) == 1
    details_str = str(records[0].details)
    assert "supersecretpassword!" not in details_str
    assert "[REDACTED_SECRET]" in details_str
    assert records[0].principle == ResponsibleAIPrinciple.PRIVACY_AND_SECURITY.value


def test_privacy_security_blocks_path_traversal(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path)
    policy = PolicyEngine(cfg)

    traversal_action = ToolCall(tool_name="read_file", arguments={"path": "../../../system.ini"})
    decision = policy.validate(traversal_action, tmp_path)
    assert decision.allowed is False
    assert decision.principle == ResponsibleAIPrinciple.PRIVACY_AND_SECURITY.value


# 4. Inclusiveness
def test_inclusiveness_diagnostics():
    info = get_principle_info(ResponsibleAIPrinciple.INCLUSIVENESS)
    assert "CLI" in info["enforcing_components"]
    assert "Plain-English" in info["agentic_mitigation"]


# 5. Transparency
def test_transparency_records_audit_trail_with_principles(tmp_path: Path):
    audit_dir = tmp_path / "audit"
    logger = AuditLogger(audit_dir=audit_dir, task_id="test-transp-01")

    logger.log(
        "PLAN_CREATED",
        {"plan": {"steps": [{"step": 1, "tool": "write_file"}]}},
        principle=ResponsibleAIPrinciple.TRANSPARENCY.value,
    )

    summary = logger.get_summary()
    assert summary["total_events"] == 1
    assert ResponsibleAIPrinciple.TRANSPARENCY.value in summary["principles_involved"]


# 6. Accountability
def test_accountability_autonomy_modes(tmp_path: Path):
    target = tmp_path / "file.txt"
    target.write_text("hello", encoding="utf-8")

    # Mode 1: Manual autonomy - ALL mutating operations require approval
    cfg_manual = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="manual")
    policy_manual = PolicyEngine(cfg_manual)

    write_action = ToolCall(tool_name="write_file", arguments={"path": "file.txt", "content": "edit"})
    dec_manual = policy_manual.validate(write_action, tmp_path)
    assert dec_manual.allowed is True
    assert dec_manual.requires_approval is True
    assert dec_manual.principle == ResponsibleAIPrinciple.ACCOUNTABILITY.value

    # Mode 2: Assisted autonomy (default) - writes are safe, deletes require approval
    cfg_assisted = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="assisted")
    policy_assisted = PolicyEngine(cfg_assisted)

    dec_assisted_write = policy_assisted.validate(write_action, tmp_path)
    assert dec_assisted_write.requires_approval is False

    delete_action = ToolCall(tool_name="delete_file", arguments={"path": "file.txt"})
    dec_assisted_delete = policy_assisted.validate(delete_action, tmp_path)
    assert dec_assisted_delete.requires_approval is True
    assert dec_assisted_delete.principle == ResponsibleAIPrinciple.ACCOUNTABILITY.value

    # Mode 3: Autonomous mode - policy-checked actions run without approval
    cfg_auto = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="autonomous")
    policy_auto = PolicyEngine(cfg_auto)

    dec_auto_delete = policy_auto.validate(delete_action, tmp_path)
    assert dec_auto_delete.allowed is True
    assert dec_auto_delete.requires_approval is False
