"""Python process execution tool with timeouts, limits, and diagnostics."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from kaufee.safety.permissions import is_path_safe_and_within_workspace
from kaufee.tools.base import BaseTool


class PythonRunnerTool(BaseTool):
    """Safely executes Python scripts or code within the workspace boundary."""

    name = "python_runner"
    description = (
        "Execute a Python script or code snippet in the workspace. "
        "Enforces strict timeout, bounded output, and captures stdout, stderr, and exit codes."
    )

    def __init__(self, default_timeout: int = 15, max_output_bytes: int = 50000):
        self.default_timeout = default_timeout
        self.max_output_bytes = max_output_bytes

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "script_path": {
                    "type": "string",
                    "description": "Relative path to python script inside workspace (e.g. 'main.py').",
                },
                "code": {
                    "type": "string",
                    "description": "Inline Python code to execute if no script_path is provided.",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional command-line arguments to pass to the script.",
                    "default": [],
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds.",
                    "default": self.default_timeout,
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        script_path_arg = arguments.get("script_path")
        inline_code = arguments.get("code")
        cli_args = arguments.get("args", [])
        timeout = int(arguments.get("timeout", self.default_timeout))

        if not script_path_arg and not inline_code:
            return False, "Either 'script_path' or 'code' must be provided.", {}

        # Determine target file to run
        if script_path_arg:
            is_safe, msg, target = is_path_safe_and_within_workspace(
                script_path_arg, workspace_root, must_exist=True
            )
            if not is_safe or target is None:
                return False, msg, {}
            if not target.is_file():
                return False, f"Script '{script_path_arg}' is not a file.", {}
            exec_target = target
        else:
            # Save inline code to a temporary run file inside .kaufee/tmp/
            tmp_dir = workspace_root / ".kaufee" / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            exec_target = tmp_dir / f"run_{int(time.time() * 1000)}.py"
            with open(exec_target, "w", encoding="utf-8") as f:
                f.write(inline_code or "")

        cmd = [sys.executable, str(exec_target)] + [str(a) for a in cli_args]

        env = os.environ.copy()
        # Set PYTHONPATH to workspace root
        env["PYTHONPATH"] = str(workspace_root)
        # Force unbuffered output
        env["PYTHONUNBUFFERED"] = "1"

        start_time = time.perf_counter()
        try:
            process = subprocess.run(
                cmd,
                cwd=str(workspace_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            stdout = process.stdout or ""
            stderr = process.stderr or ""

            # Truncate if exceeds bounds
            if len(stdout) > self.max_output_bytes:
                stdout = stdout[: self.max_output_bytes] + "\n...[stdout truncated]..."
            if len(stderr) > self.max_output_bytes:
                stderr = stderr[: self.max_output_bytes] + "\n...[stderr truncated]..."

            metadata = {
                "returncode": process.returncode,
                "duration_ms": duration_ms,
                "stdout": stdout,
                "stderr": stderr,
                "script": str(exec_target.name),
            }

            if process.returncode == 0:
                output_str = stdout if stdout else "(Execution completed with exit code 0 and empty output)"
                return True, output_str, metadata
            else:
                err_report = f"Execution failed (exit code {process.returncode}):\n"
                if stderr:
                    err_report += f"STDERR:\n{stderr}\n"
                if stdout:
                    err_report += f"STDOUT:\n{stdout}\n"
                return False, err_report.strip(), metadata

        except subprocess.TimeoutExpired:
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return (
                False,
                f"Execution timed out after {timeout} seconds.",
                {"returncode": -1, "duration_ms": duration_ms, "timeout": timeout},
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return (
                False,
                f"Failed to spawn Python process: {exc}",
                {"returncode": -1, "duration_ms": duration_ms, "error": str(exc)},
            )
