"""Integration test for file reorganization and multi-step management."""

from pathlib import Path
from kaufee.agent.controller import AgentController
from kaufee.config import KaufeeConfig
from kaufee.llm.mock import MockLLMClient
from kaufee.state.models import TaskStatus


def test_file_organize_end_to_end(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Pre-create sample files
    sample_txt = workspace / "sample.txt"
    sample_txt.write_text("Sample file content", encoding="utf-8")

    cfg = KaufeeConfig(
        workspace_root=workspace,
        llm_provider="mock",
        audit_dir=workspace / ".kaufee" / "audit",
    )

    mock_llm = MockLLMClient()
    controller = AgentController(config=cfg, llm_client=mock_llm)

    goal = "Organize files by moving sample.txt into texts directory."
    state = controller.run_task(goal=goal)

    assert state.status == TaskStatus.COMPLETED
    assert not sample_txt.exists()
    assert (workspace / "texts" / "sample.txt").exists()
