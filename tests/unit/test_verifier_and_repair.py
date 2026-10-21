"""Unit tests for query task verification and repair loop handling."""

from pathlib import Path
from kaufee.agent.verifier import Verifier
from kaufee.state.models import TaskState, TaskStatus, VerificationCheck


def test_verifier_read_only_task_success(tmp_path: Path):
    verifier = Verifier(tmp_path)
    state = TaskState(goal="Tell me the names of the files in the workspace", workspace_root=str(tmp_path))
    state.history.append({
        "action": {"tool_name": "list_files", "arguments": {"directory": "."}},
        "result": {"success": True, "output": "Directory is empty.", "error": None},
        "status": "SUCCESS",
    })

    result = verifier.verify(state.goal, state)
    assert result.success is True
    assert len(result.checks) == 1
    assert result.checks[0].passed is True
    assert result.checks[0].name == "task_execution"


def test_verifier_read_only_task_failure(tmp_path: Path):
    verifier = Verifier(tmp_path)
    state = TaskState(goal="Tell me the names of the files in the workspace", workspace_root=str(tmp_path))
    state.history.append({
        "action": {"tool_name": "list_files", "arguments": {"directory": "."}},
        "result": {"success": False, "output": "", "error": "Permission denied"},
        "status": "FAILED",
    })

    result = verifier.verify(state.goal, state)
    assert result.success is False
    assert any(not c.passed for c in result.checks)


def test_triangle_verification_reuses_runner_output(tmp_path: Path):
    (tmp_path / "triangle.py").write_text("print('*')\n", encoding="utf-8")
    verifier = Verifier(tmp_path)
    state = TaskState(goal="Create and run a triangle", workspace_root=str(tmp_path))
    state.history.extend([
        {
            "action": {"tool_name": "write_file", "arguments": {"path": "triangle.py"}},
            "result": {"success": True},
        },
        {
            "action": {"tool_name": "python_runner", "arguments": {"script_path": "triangle.py"}},
            "result": {"success": True, "output": "*"},
        },
    ])

    result = verifier.verify(state.goal, state)
    triangle_check = next(check for check in result.checks if check.name == "triangle_pattern_output")
    assert triangle_check.passed


def test_verifier_does_not_execute_script_without_approved_runner_result(tmp_path: Path):
    sentinel = tmp_path / "verifier_ran_code.txt"
    script = tmp_path / "payload.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    state = TaskState(goal="Run payload.py", workspace_root=str(tmp_path))
    state.history.append({
        "action": {"tool_name": "write_file", "arguments": {"path": "payload.py"}},
        "result": {"success": True},
        "status": "SUCCESS",
    })

    result = Verifier(tmp_path).verify(state.goal, state)

    code_execution = next(check for check in result.checks if check.name == "code_execution")
    assert not code_execution.passed
    assert not sentinel.exists()
