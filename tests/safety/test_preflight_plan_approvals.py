"""Tests for pre-flight plan approval gates and eliminating approval fatigue."""

from pathlib import Path
from kaufee.agent.controller import AgentController
from kaufee.config import KaufeeConfig
from kaufee.llm.mock import MockLLMClient
from kaufee.state.models import Plan, TaskStatus


def test_preflight_plan_approval_accept_bypasses_step_prompts(tmp_path: Path):
    """When plan is approved upfront, planned mutating actions execute without secondary step prompts."""
    cfg = KaufeeConfig(
        workspace_root=tmp_path,
        llm_provider="mock",
        approval_mode="plan",
        autonomy_mode="assisted",
        require_approval_for_delete=True,
    )

    mock_llm = MockLLMClient()
    controller = AgentController(config=cfg, llm_client=mock_llm)

    step_prompt_count = 0

    def step_approval_callback(action, decision):
        nonlocal step_prompt_count
        step_prompt_count += 1
        return True

    plan_prompt_count = 0

    def plan_approval_callback(plan: Plan):
        nonlocal plan_prompt_count
        plan_prompt_count += 1
        return True

    state = controller.run_task(
        goal="Create a test file and write content",
        approval_callback=step_approval_callback,
        plan_approval_callback=plan_approval_callback,
    )

    assert plan_prompt_count == 1
    # Step prompts were bypassed because the plan was approved upfront!
    assert step_prompt_count == 0
    assert state.plan_approved is True
    assert state.status == TaskStatus.COMPLETED


def test_preflight_plan_rejection_halts_task(tmp_path: Path):
    """When upfront plan is rejected, execution halts immediately."""
    cfg = KaufeeConfig(
        workspace_root=tmp_path,
        llm_provider="mock",
        approval_mode="plan",
        autonomy_mode="assisted",
    )

    mock_llm = MockLLMClient()
    controller = AgentController(config=cfg, llm_client=mock_llm)

    state = controller.run_task(
        goal="Create a test file",
        plan_approval_callback=lambda plan: False,  # User rejects plan
    )

    assert state.status == TaskStatus.FAILED
    assert "not approved" in state.error_message.lower() or "rejected" in state.error_message.lower()
