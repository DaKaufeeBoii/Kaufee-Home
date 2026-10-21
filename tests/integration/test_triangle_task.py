"""Deterministic end-to-end integration test for the triangle task."""

from pathlib import Path
from kaufee.agent.controller import AgentController
from kaufee.config import KaufeeConfig
from kaufee.llm.mock import MockLLMClient
from kaufee.state.models import TaskStatus


def test_triangle_task_end_to_end(tmp_path: Path):
    """
    Simulates the core MVP goal:
    kaufee> Create a Python program that draws a triangle, run it, and fix any errors.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    cfg = KaufeeConfig(
        workspace_root=workspace,
        llm_provider="mock",
        audit_dir=workspace / ".kaufee" / "audit",
    )

    mock_llm = MockLLMClient()
    controller = AgentController(config=cfg, llm_client=mock_llm)

    goal = "Create a Python program that draws a triangle, run it, and fix any errors."
    state = controller.run_task(goal=goal, approval_callback=lambda _action, _decision: True)

    assert state.status == TaskStatus.COMPLETED
    assert state.verification_result is not None
    assert state.verification_result.success is True

    # Verify physical file existence and execution
    triangle_file = workspace / "triangle.py"
    assert triangle_file.exists()
    assert triangle_file.stat().st_size > 0

    content = triangle_file.read_text(encoding="utf-8")
    assert "draw_triangle" in content

    # Verify audit log was created
    audit_files = list((workspace / ".kaufee" / "audit").glob("*.audit.json"))
    assert len(audit_files) > 0
