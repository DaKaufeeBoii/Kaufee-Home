"""Python process execution tool with timeouts, limits, and diagnostics."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from kaufee.safety.permissions import is_path_safe_and_within_workspace
from kaufee.tools.base import BaseTool


class PythonRunnerTool(BaseTool):
    """Execute workspace Python code with bounded time and captured output.

    This is resource limiting, not a security sandbox: child Python code still
    runs with the current user's OS permissions.
    """

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
    ):
        self.default_timeout = max(1, int(default_timeout))
        self.max_output_bytes = max(1, int(max_output_bytes))
        self.cancellation_event = cancellation_event or threading.Event()

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

        cmd = [sys.executable, str(exec_target), *[str(arg) for arg in cli_args]]
        # Avoid leaking API keys and unrelated parent-process state to generated code.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "WINDIR": os.environ.get("WINDIR", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": str(workspace),
        }
        start_time = time.perf_counter()
        try:
            # File-backed output avoids unbounded in-memory PIPE buffering while
            # retaining only the configured number of bytes for the result.
            with (
                tempfile.TemporaryFile(mode="w+b") as stdout_file,
                tempfile.TemporaryFile(mode="w+b") as stderr_file,
                tempfile.TemporaryFile(mode="w+b") as stdin_file,
            ):
                if stdin_text is not None:
                    stdin_file.write(stdin_text.encode("utf-8"))
                    stdin_file.seek(0)
                process = subprocess.Popen(
                    cmd,
                    cwd=str(workspace),
                    stdin=stdin_file if stdin_text is not None else subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env=env,
                )
                timed_out = False
                cancelled = False
                deadline = start_time + timeout
                while process.poll() is None:
                    if self.cancellation_event.is_set():
                        cancelled = True
                        process.kill()
                        process.wait()
                        break
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        timed_out = True
                        process.kill()
                        process.wait()
                        break
                    try:
                        process.wait(timeout=min(0.1, remaining))
                    except subprocess.TimeoutExpired:
                        continue
                    except KeyboardInterrupt:
                        cancelled = True
                        self.cancellation_event.set()
                        process.kill()
                        process.wait()
                        break

                duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                output_truncated = (
                    stdout_file.seek(0, os.SEEK_END) > self.max_output_bytes
                    or stderr_file.seek(0, os.SEEK_END) > self.max_output_bytes
                )
                stdout = self._read_bounded(stdout_file)
                stderr = self._read_bounded(stderr_file)
                metadata = {
                    "returncode": -1 if timed_out else process.returncode,
                    "duration_ms": duration_ms,
                    "stdout": stdout,
                    "stderr": stderr,
                    "script": exec_target.name,
                    "output_truncated": output_truncated,
                }
                if timed_out:
                    metadata["timeout"] = timeout
                    return False, f"Execution timed out after {timeout} seconds.", metadata
                if cancelled:
                    metadata["cancelled"] = True
                    return False, "Execution cancelled by user.", metadata
                if process.returncode == 0:
                    return True, stdout or "(Execution completed with exit code 0 and empty output)", metadata
                report = f"Execution failed (exit code {process.returncode}):"
                if stderr:
                    report += f"\nSTDERR:\n{stderr}"
                if stdout:
                    report += f"\nSTDOUT:\n{stdout}"
                return False, report, metadata
        except Exception as exc:
            return False, f"Failed to spawn Python process: {exc}", {
                "returncode": -1,
                "duration_ms": round((time.perf_counter() - start_time) * 1000.0, 2),
                "error": str(exc),
            }
        finally:
            if temporary_script is not None:
                try:
                    Path(temporary_script.name).unlink(missing_ok=True)
                except OSError:
                    pass

    def _read_bounded(self, stream: Any) -> str:
        stream.seek(0)
        data = stream.read(self.max_output_bytes + 1)
        truncated = len(data) > self.max_output_bytes
        data = data[: self.max_output_bytes]
        result = data.decode("utf-8", errors="replace")
        if truncated:
            result += "\n...[stream truncated]..."
        return result
