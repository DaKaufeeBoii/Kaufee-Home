"""Independent verifier to check postconditions, syntax, and execution outcomes."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional
from kaufee.state.models import TaskState, VerificationCheck, VerificationResult


class Verifier:
    """Verifies that task postconditions are objectively met."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def verify(self, goal: str, state: TaskState) -> VerificationResult:
        """
        Run objective verification checks on task outcomes.
        Does NOT trust model self-reporting.
        """
        checks: list[VerificationCheck] = []
        lower_goal = goal.lower()

        # 1. Audit check: were any tools run at all?
        if not state.history:
            return VerificationResult(
                success=False,
                message="No actions were performed during task execution.",
                checks=[VerificationCheck(name="execution_history", passed=False, details="History is empty.")],
            )

        # 2. Check all files created or modified in history
        modified_files: set[str] = set()
        last_python_run_success: Optional[bool] = None
        last_python_output = ""

        for entry in state.history:
            action = entry.get("action", {})
            result = entry.get("result", {})
            args = action.get("arguments", {})

            for key in ["path", "destination_path"]:
                if key in args:
                    modified_files.add(args[key])

            if action.get("tool_name") == "python_runner":
                last_python_run_success = result.get("success", False)
                last_python_output = result.get("output", "")

        # Verify modified files exist and have non-zero size
        for rel_file in modified_files:
            file_path = self.workspace_root / rel_file

            # Skip __init__.py — empty __init__.py is valid Python convention
            # and is often created as a directory-creation side effect
            is_init = file_path.name == "__init__.py"

            if not file_path.exists():
                if is_init:
                    continue  # Don't fail for missing __init__.py
                checks.append(
                    VerificationCheck(
                        name=f"file_exists_{rel_file}",
                        passed=False,
                        details=f"Expected file '{rel_file}' was not found on disk.",
                    )
                )
                continue

            size = file_path.stat().st_size

            if not is_init:
                checks.append(
                    VerificationCheck(
                        name=f"file_non_empty_{rel_file}",
                        passed=size > 0,
                        details=f"File '{rel_file}' exists with size {size} bytes.",
                    )
                )

            # Check Python AST syntax validity if .py file, non-empty, and not __init__.py
            if file_path.suffix == ".py" and not is_init:
                if size == 0:
                    checks.append(
                        VerificationCheck(
                            name=f"syntax_valid_{rel_file}",
                            passed=False,
                            details=f"File '{rel_file}' is empty — no code was written.",
                        )
                    )
                else:
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            code = f.read()
                        ast.parse(code)
                        checks.append(
                            VerificationCheck(
                                name=f"syntax_valid_{rel_file}",
                                passed=True,
                                details=f"Python syntax parsed cleanly for '{rel_file}'.",
                            )
                        )
                    except SyntaxError as syn_err:
                        checks.append(
                            VerificationCheck(
                                name=f"syntax_valid_{rel_file}",
                                passed=False,
                                details=f"SyntaxError in '{rel_file}': {syn_err}",
                            )
                        )

        # 3. Check code execution postconditions if task required running code
        requires_execution = any(
            kw in lower_goal
            for kw in ["run", "execute", "triangle", "fix any error", "fix the error", "repair"]
        )

        if requires_execution:
            if last_python_run_success is None:
                checks.append(
                    VerificationCheck(
                        name="code_execution",
                        passed=False,
                        details="Execution was required but no approved Python runner result was recorded.",
                    )
                )
            else:
                checks.append(
                    VerificationCheck(
                        name="code_execution",
                        passed=last_python_run_success,
                        details=(
                            "Python script executed successfully with exit code 0."
                            if last_python_run_success
                            else "Last Python execution failed or produced an error."
                        ),
                    )
                )

        # 4. Domain specific postconditions
        # Triangle check
        if "triangle" in lower_goal:
            triangle_path = self.workspace_root / "triangle.py"
            if triangle_path.exists():
                if last_python_run_success is None:
                    run_succeeded = False
                    run_output = "No approved Python runner result was recorded."
                else:
                    run_succeeded = last_python_run_success
                    run_output = last_python_output
                has_triangle_pattern = any(mark in run_output for mark in ("*", "^", "#"))
                checks.append(
                    VerificationCheck(
                        name="triangle_pattern_output",
                        passed=run_succeeded and has_triangle_pattern,
                        details=(
                            f"Triangle output verified: {run_output[:100]}..."
                            if (run_succeeded and has_triangle_pattern)
                            else "Triangle program execution did not produce expected pattern."
                        ),
                    )
                )

        # 5. Fallback for read-only/query tasks where no files were modified
        if not checks:
            non_verify_history = [
                entry for entry in state.history
                if entry.get("action", {}).get("tool_name") != "verify"
            ]
            has_success = any(
                entry.get("result", {}).get("success", False)
                for entry in non_verify_history
            )
            no_failures = not any(
                entry.get("status") in ("FAILED", "BLOCKED", "DENIED")
                for entry in non_verify_history
            )
            passed = bool(non_verify_history) and has_success and no_failures
            checks.append(
                VerificationCheck(
                    name="task_execution",
                    passed=passed,
                    details=(
                        "All planned actions executed successfully without errors."
                        if passed
                        else "Task actions failed or history was incomplete."
                    ),
                )
            )

        # Overall success: all checks must pass and no fatal check failed
        all_passed = bool(checks) and all(c.passed for c in checks)
        msg = (
            f"All {len(checks)} verification check(s) passed successfully."
            if all_passed
            else f"Verification failed: {sum(1 for c in checks if not c.passed)} check(s) did not pass."
        )

        return VerificationResult(success=all_passed, message=msg, checks=checks)
