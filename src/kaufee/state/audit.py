"""Audit logging for tracking every action, approval, decision, and outcome."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from kaufee.state.models import AuditRecord


class AuditLogger:
    """Records structured audit events to file and memory."""

    def __init__(self, audit_dir: Path, task_id: str):
        self.audit_dir = audit_dir
        self.task_id = task_id
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.audit_dir / f"{task_id}.audit.json"
        self.records: list[AuditRecord] = []

    def log(self, event_type: str, details: Optional[dict[str, Any]] = None) -> AuditRecord:
        """Log a new audit record to file and memory."""
        record = AuditRecord(
            task_id=self.task_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            details=details or {},
        )
        self.records.append(record)
        self._write_to_disk(record)
        return record

    def _write_to_disk(self, record: AuditRecord) -> None:
        """Append line to jsonl or rewrite json array."""
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.model_dump(), default=str) + "\n")
        except Exception:
            pass

    def get_summary(self) -> dict[str, Any]:
        """Aggregate summary metrics from recorded events."""
        tool_calls = [r for r in self.records if r.event_type == "TOOL_EXEC"]
        tool_succeeded = [
            r for r in tool_calls if r.details.get("result", {}).get("success") is True
        ]
        tool_failed = [
            r for r in tool_calls if r.details.get("result", {}).get("success") is False
        ]
        policy_blocked = [
            r for r in self.records if r.event_type == "POLICY_DECISION" and not r.details.get("allowed")
        ]
        approvals = [r for r in self.records if r.event_type == "APPROVAL_PROMPT"]

        return {
            "task_id": self.task_id,
            "total_events": len(self.records),
            "tool_calls_attempted": len(tool_calls),
            "tool_calls_succeeded": len(tool_succeeded),
            "tool_calls_failed": len(tool_failed),
            "policy_blocked_actions": len(policy_blocked),
            "approval_requests": len(approvals),
            "log_path": str(self.log_file),
        }

    @classmethod
    def load_task_records(cls, log_file: Path) -> list[AuditRecord]:
        """Load records from an audit log file."""
        if not log_file.is_file():
            return []
        records = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        records.append(AuditRecord(**data))
                    except Exception:
                        pass
        return records
