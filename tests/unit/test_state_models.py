"""Unit tests for state models and task lifecycle."""

from kaufee.state.models import (
    Plan,
    PlanStep,
    StepStatus,
    TaskState,
    TaskStatus,
    ToolCall,
    ToolResult,
    VerificationCheck,
    VerificationResult,
)


def test_task_state_lifecycle():
    state = TaskState(goal="Test goal", workspace_root="/tmp/ws")
    assert state.status == TaskStatus.PENDING
    assert state.is_cancelled() is False

    # Complete
    v_res = VerificationResult(
        success=True,
        message="All good",
        checks=[VerificationCheck(name="test", passed=True, details="ok")],
    )
    state.complete(v_res)
    assert state.status == TaskStatus.COMPLETED
    assert state.verification_result == v_res
    assert state.completed_at is not None


def test_task_state_cancellation():
    state = TaskState(goal="Cancel goal", workspace_root="/tmp/ws")
    state.cancel("User pressed stop")
    assert state.status == TaskStatus.CANCELLED
    assert state.is_cancelled() is True
    assert state.error_message == "User pressed stop"


def test_plan_and_steps():
    step1 = PlanStep(
        step_number=1,
        description="Write code",
        tool_name="write_file",
        arguments={"path": "app.py", "content": "print(1)"},
    )
    plan = Plan(goal="Write app", steps=[step1])
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "write_file"
