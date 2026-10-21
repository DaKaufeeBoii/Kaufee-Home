"""Deterministic integration test for diagnosing and repairing a syntax error."""

from pathlib import Path
from kaufee.agent.controller import AgentController
from kaufee.config import KaufeeConfig
from kaufee.llm.mock import MockLLMClient
from kaufee.state.models import TaskStatus


def test_syntax_repair_end_to_end(tmp_path: Path):
    """
    Goal: Fix syntax error in broken.py, run it, and verify completion.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Pre-create a deliberately broken Python file
    broken_py = workspace / "broken.py"
    broken_py.write_text("def broken_func(\n    print('Missing closing parenthesis')\n", encoding="utf-8")

    cfg = KaufeeConfig(
        workspace_root=workspace,
        llm_provider="mock",
        audit_dir=workspace / ".kaufee" / "audit",
    )

    mock_llm = MockLLMClient()
    controller = AgentController(config=cfg, llm_client=mock_llm)

    goal = "Fix the syntax error in broken.py, run it, and verify the output."
    state = controller.run_task(goal=goal, approval_callback=lambda _action, _decision: True)

    assert state.status == TaskStatus.COMPLETED
    assert state.verification_result is not None
    assert state.verification_result.success is True

    # Verify broken.py is fixed and runs cleanly
    fixed_content = broken_py.read_text(encoding="utf-8")
    assert "print('Fixed syntax error')" in fixed_content
