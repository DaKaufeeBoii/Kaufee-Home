"""Safety tests verifying that the agent cannot escape the workspace."""

from pathlib import Path
from kaufee.config import KaufeeConfig
from kaufee.safety.permissions import is_path_safe_and_within_workspace
from kaufee.safety.policy import PolicyEngine
from kaufee.state.models import RiskLevel, ToolCall


def test_path_traversal_blocked(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Attempting to access parent directory
    unsafe_paths = [
        "../outside.txt",
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "..\\..\\outside.txt",
        "sub/../../secret.txt",
    ]

    for p in unsafe_paths:
        is_safe, msg, resolved = is_path_safe_and_within_workspace(p, workspace)
        assert is_safe is False
        assert "traversal blocked" in msg.lower() or "outside workspace" in msg.lower()


def test_protected_files_blocked(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    protected_targets = [
        ".kaufee/backups/backups_manifest.json",
        ".git",
        ".env",
        ".ENV.local",
        "id_rsa",
        "nested/.ssh/known_hosts",
        "windows\\system32\\config",
        r"nested\.ssh\known_hosts",
    ]

    for p in protected_targets:
        is_safe, msg, resolved = is_path_safe_and_within_workspace(p, workspace)
        assert is_safe is False
        assert "protected" in msg.lower()


def test_protected_path_components_are_case_insensitive(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    for target in (".GIT/config", "nested/.AWS/credentials", "nested/.ENV.local"):
        safe, reason, _ = is_path_safe_and_within_workspace(target, workspace)
        assert not safe
        assert "protected" in reason.lower()


def test_symlinks_inside_workspace_are_rejected(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    actual = workspace / "actual.txt"
    actual.write_text("data", encoding="utf-8")
    link = workspace / "linked.txt"
    try:
        link.symlink_to(actual)
    except OSError:
        return

    safe, reason, resolved = is_path_safe_and_within_workspace(link, workspace, must_exist=True)
    assert not safe
    assert "symbolic link" in reason.lower()
    assert resolved is None


def test_policy_engine_blocks_outside_access(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cfg = KaufeeConfig(workspace_root=workspace)
    policy = PolicyEngine(cfg)

    action = ToolCall(
        tool_name="read_file",
        arguments={"path": "../../../system_file.txt"},
    )
    decision = policy.validate(action, workspace)
    assert decision.allowed is False
    assert decision.risk_level == RiskLevel.CRITICAL
