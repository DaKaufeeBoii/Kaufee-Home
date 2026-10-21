"""Independent verifier to check postconditions, syntax, and execution outcomes."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
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
            if not file_path.exists():
                checks.append(
                    VerificationCheck(
                        name=f"file_exists_{rel_file}",
                        passed=False,
                        details=f"Expected file '{rel_file}' was not found on disk.",
                    )
                )
                continue

            size = file_path.stat().st_size
            checks.append(
                VerificationCheck(
                    name=f"file_non_empty_{rel_file}",
                    passed=size > 0,
                    details=f"File '{rel_file}' exists with size {size} bytes.",
                )
            )

            # Check Python AST syntax validity if .py file
            if file_path.suffix == ".py":
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
                # If script was created but not executed, verify by executing it now
                py_files = [f for f in modified_files if f.endswith(".py")]
                if py_files:
                    target_script = self.workspace_root / py_files[0]
                    res = self._execute_script_check(target_script)
                    checks.append(res)
                else:
                    checks.append(
                        VerificationCheck(
                            name="code_execution",
                            passed=False,
                            details="Task required code execution, but no Python script was executed or found.",
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
                res = self._execute_script_check(triangle_path)
                has_triangle_pattern = "*" in res.details or "^" in res.details or "#" in res.details
                checks.append(
                    VerificationCheck(
                        name="triangle_pattern_output",
                        passed=res.passed and has_triangle_pattern,
                        details=(
                            f"Triangle output verified: {res.details[:100]}..."
                            if (res.passed and has_triangle_pattern)
                            else "Triangle program execution did not produce expected pattern."
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

    def _execute_script_check(self, script_path: Path) -> VerificationCheck:
        """Run script in subprocess for independent verification."""
        try:
            res = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(self.workspace_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if res.returncode == 0:
                return VerificationCheck(
                    name=f"independent_run_{script_path.name}",
                    passed=True,
                    details=res.stdout.strip() or "Exit code 0",
                )
            else:
                return VerificationCheck(
                    name=f"independent_run_{script_path.name}",
                    passed=False,
                    details=f"Exit code {res.returncode}. Stderr: {res.stderr.strip()}",
                )
        except Exception as exc:
            return VerificationCheck(
                name=f"independent_run_{script_path.name}",
                passed=False,
                details=f"Verification run exception: {exc}",
            )
