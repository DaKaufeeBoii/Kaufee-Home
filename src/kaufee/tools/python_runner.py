"""Python process execution tool with timeouts, limits, sandboxing, and diagnostics."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any

from kaufee.safety.permissions import is_path_safe_and_within_workspace
from kaufee.tools.base import BaseTool
from kaufee.tools.runner_base import BaseExecutionRunner, DockerRunner, SubprocessRunner


class PythonRunnerTool(BaseTool):
    """Execute workspace Python code with bounded time, captured output, and optional Docker sandboxing."""

    name = "python_runner"
    description = (
        "Execute a Python script or code snippet in the workspace. "
        "Enforces a timeout and bounded captured output."
    )

    def __init__(
        self,
        default_timeout: int = 15,
        max_output_bytes: int = 50000,
        cancellation_event: threading.Event | None = None,
        runner: BaseExecutionRunner | None = None,
        runner_type: str = "auto",
    ):
        self.default_timeout = max(1, int(default_timeout))
        self.max_output_bytes = max(1, int(max_output_bytes))
        self.cancellation_event = cancellation_event or threading.Event()
        self.runner_type = runner_type
        if runner is not None:
            self._runner = runner
        elif runner_type == "docker":
            self._runner = DockerRunner()
        elif runner_type == "auto":
            docker = DockerRunner()
            self._runner = docker if docker.is_available() else SubprocessRunner()
        else:
            self._runner = SubprocessRunner()

    @property
    def runner(self) -> BaseExecutionRunner:
        return self._runner

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "script_path": {"type": "string", "description": "Relative Python script path."},
                "code": {"type": "string", "description": "Inline Python code when script_path is omitted."},
                "args": {"type": "array", "items": {"type": "string"}, "default": []},
                "stdin": {
                    "type": "string",
                    "description": "Optional text supplied to the program's standard input, including newline separators.",
                },
                "timeout": {"type": "integer", "description": "Execution timeout in seconds."},
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        script_path_arg = arguments.get("script_path")
        inline_code = arguments.get("code")
        cli_args = arguments.get("args", [])
        stdin_text = arguments.get("stdin")
        try:
            timeout = int(arguments.get("timeout", self.default_timeout))
        except (TypeError, ValueError):
            return False, "Argument 'timeout' must be a positive integer.", {}
        if timeout < 1:
            return False, "Argument 'timeout' must be a positive integer.", {}
        if not isinstance(cli_args, list) or any(not isinstance(arg, (str, int, float)) for arg in cli_args):
            return False, "Argument 'args' must be a list of strings or numbers.", {}
        if stdin_text is not None and not isinstance(stdin_text, str):
            return False, "Argument 'stdin' must be a string when provided.", {}
        if bool(script_path_arg) == (inline_code is not None):
            return False, "Provide exactly one of 'script_path' or 'code'.", {}

        workspace = workspace_root.resolve()
        temporary_script: tempfile.NamedTemporaryFile | None = None
        if script_path_arg:
            safe, message, target = is_path_safe_and_within_workspace(
                script_path_arg, workspace, must_exist=True
            )
            if not safe or target is None:
                return False, message, {}
            if not target.is_file():
                return False, f"Script '{script_path_arg}' is not a file.", {}
            exec_target = target
        else:
            temp_dir = workspace / ".kaufee" / "tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temporary_script = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".py", prefix="run_", dir=temp_dir, delete=False
            )
            temporary_script.write(inline_code)
            temporary_script.close()
            exec_target = Path(temporary_script.name)

        try:
            return self._runner.execute(
                exec_target,
                cli_args,
                workspace,
                stdin_text,
                timeout,
                self.max_output_bytes,
                self.cancellation_event,
            )
        finally:
            if temporary_script is not None:
                try:
                    Path(temporary_script.name).unlink(missing_ok=True)
                except OSError:
                    pass
