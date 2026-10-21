"""Typed state and data models for Kaufee-Home."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(str, Enum):
    """Lifecycle status of a task."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    """Lifecycle status of an individual plan step."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class RiskLevel(str, Enum):
    """Risk classification for policy assessment."""
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PolicyDecision(BaseModel):
    """Result of policy evaluation for a proposed action."""
    allowed: bool
    requires_approval: bool = False
    reason: str
    risk_level: RiskLevel = RiskLevel.SAFE


class ToolCall(BaseModel):
    """A proposed action requesting tool execution."""
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None


class ToolResult(BaseModel):
    """Outcome of executing a tool."""
    call_id: str
    tool_name: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    """An individual atomic step inside a plan."""
    step_number: int
    description: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_outcome: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Optional[ToolResult] = None


class Plan(BaseModel):
    """Structured plan generated for a task goal."""
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)


class VerificationCheck(BaseModel):
    """Individual assertion check in postcondition verification."""
    name: str
    passed: bool
    details: str = ""


class VerificationResult(BaseModel):
    """Comprehensive outcome of verifying task completion."""
    success: bool
    message: str
    checks: list[VerificationCheck] = Field(default_factory=list)


class AuditRecord(BaseModel):
    """Structured record of an action, decision, or event."""
    timestamp: str = Field(default_factory=_utc_now_iso)
    task_id: str
    event_type: str  # e.g., "TASK_START", "POLICY_CHECK", "TOOL_EXEC", "APPROVAL", "VERIFY"
    details: dict[str, Any] = Field(default_factory=dict)


class TaskState(BaseModel):
    """Full execution state of a Kaufee task."""
    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:10]}")
    goal: str
    workspace_root: str
    status: TaskStatus = TaskStatus.PENDING
    plan: Optional[Plan] = None
    current_step_index: int = 0
    repair_count: int = 0
    max_steps: int = 12
    max_repairs: int = 3
    tool_calls_attempted: int = 0
    tool_calls_succeeded: int = 0
    tool_calls_failed: int = 0
    history: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    verification_result: Optional[VerificationResult] = None
    is_cancelled_flag: bool = False

    def is_cancelled(self) -> bool:
        return self.is_cancelled_flag

    def cancel(self, reason: str = "Task cancelled by user") -> TaskState:
        self.is_cancelled_flag = True
        self.status = TaskStatus.CANCELLED
        self.completed_at = _utc_now_iso()
        self.error_message = reason
        return self

    def complete(self, result: VerificationResult) -> TaskState:
        self.status = TaskStatus.COMPLETED
        self.completed_at = _utc_now_iso()
        self.verification_result = result
        return self

    def fail(self, reason: str) -> TaskState:
        self.status = TaskStatus.FAILED
        self.completed_at = _utc_now_iso()
        self.error_message = reason
        return self

    def plan_is_complete(self) -> bool:
        if not self.plan or not self.plan.steps:
            return False
        return self.current_step_index >= len(self.plan.steps)
