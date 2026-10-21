"""Policy engine to evaluate and authorize every tool call before execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from kaufee.config import KaufeeConfig
from kaufee.safety.permissions import is_path_safe_and_within_workspace
from kaufee.state.models import PolicyDecision, RiskLevel, ToolCall


class PolicyEngine:
    """Enforces safety rules, workspace boundaries, and approval requirements."""

    def __init__(self, config: KaufeeConfig):
        self.config = config

    def validate(self, action: ToolCall, workspace_root: Path) -> PolicyDecision:
        """Validate proposed action against security policy and workspace boundary."""
        tool_name = action.tool_name.lower().strip()
        args = action.arguments or {}

        # 1. Block arbitrary shell by default
        if tool_name in ("run_shell", "bash", "cmd", "powershell", "execute_command"):
            if not self.config.allow_arbitrary_shell:
                return PolicyDecision(
                    allowed=False,
                    requires_approval=False,
                    reason="Arbitrary shell execution is disabled by default in Kaufee-Home.",
                    risk_level=RiskLevel.CRITICAL,
                )
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                reason="Shell execution requires explicit user authorization.",
                risk_level=RiskLevel.HIGH,
            )

        # 2. Package installation
        if tool_name in ("install_package", "pip_install"):
            if self.config.require_approval_for_install:
                return PolicyDecision(
                    allowed=True,
                    requires_approval=True,
                    reason="Package installation requires explicit user approval.",
                    risk_level=RiskLevel.HIGH,
                )
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                reason="Package installation allowed per configuration.",
                risk_level=RiskLevel.MEDIUM,
            )

        # 3. Path-based filesystem tools
        path_keys = ["path", "file_path", "source_path", "destination_path", "source", "destination", "directory"]
        for key in path_keys:
            if key in args and isinstance(args[key], (str, Path)):
                target = args[key]
                must_exist = key in ("source_path", "source") or (
                    key in ("path", "file_path", "directory")
                    and tool_name in ("read_file", "edit_file", "delete_file", "list_files", "undo_file")
                )
                is_safe, reason, _ = is_path_safe_and_within_workspace(
                    target, workspace_root, must_exist=must_exist
                )
                if not is_safe:
                    invalid_target = reason.startswith("Target path does not exist:")
                    return PolicyDecision(
                        allowed=False,
                        requires_approval=False,
                        reason=reason,
                        risk_level=RiskLevel.LOW if invalid_target else RiskLevel.CRITICAL,
                    )

        # 4. Destructive file operations
        if tool_name in ("delete_file", "delete_directory", "remove_file"):
            if self.config.require_approval_for_delete:
                return PolicyDecision(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Deleting '{args.get('path')}' is destructive and requires explicit approval.",
                    risk_level=RiskLevel.HIGH,
                )
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                reason="File deletion permitted per configuration.",
                risk_level=RiskLevel.MEDIUM,
            )

        # 5. Python execution tool
        if tool_name in ("python_runner", "run_python", "execute_python"):
            script_path = args.get("script_path")
            if script_path:
                is_safe, reason, _ = is_path_safe_and_within_workspace(
                    script_path, workspace_root, must_exist=True
                )
                if not is_safe:
                    return PolicyDecision(
                        allowed=False,
                        requires_approval=False,
                        reason=reason,
                        risk_level=RiskLevel.CRITICAL,
                    )
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                reason="Python execution permitted within bounded workspace.",
                risk_level=RiskLevel.LOW,
            )

        # 6. Read / Write / Edit / List files
        if tool_name in (
            "read_file", "write_file", "edit_file", "list_files", "create_directory", "move_file", "undo_file"
        ):
            if tool_name == "move_file" and args.get("overwrite", False):
                return PolicyDecision(
                    allowed=True,
                    requires_approval=self.config.require_approval_for_delete,
                    reason="Replacing a destination file is destructive and requires explicit approval."
                    if self.config.require_approval_for_delete
                    else "Move permitted; destination overwrite is enabled by configuration.",
                    risk_level=RiskLevel.HIGH if self.config.require_approval_for_delete else RiskLevel.MEDIUM,
                )
            return PolicyDecision(
                allowed=True,
                requires_approval=False,
                reason=f"Operation '{tool_name}' permitted within workspace boundary.",
                risk_level=RiskLevel.SAFE,
            )

        # Unknown tool
        return PolicyDecision(
            allowed=False,
            requires_approval=False,
            reason=f"Unrecognized or unregistered tool '{tool_name}'.",
            risk_level=RiskLevel.CRITICAL,
        )
