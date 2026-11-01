"""Abstract execution runner base protocol and implementations."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class BaseExecutionRunner(ABC):
    """Abstract interface for executing Python processes."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the runner backend."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this execution runner backend is functional in the current environment."""
        pass

    @abstractmethod
    def execute(
        self,
        exec_target: Path,
        cli_args: list[Any],
        workspace: Path,
        stdin_text: Optional[str],
        timeout: int,
        max_output_bytes: int,
        cancellation_event: threading.Event,
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        Execute python script.
        Returns:
            (success: bool, output_or_error: str, metadata: dict)
        """
        pass

    @staticmethod
    def decode_capture(data: bytearray, total_size: int) -> str:
        """Decode retained stream bytes and mark output that exceeded its cap."""
        result = bytes(data).decode("utf-8", errors="replace")
        if total_size > len(data):
            result += "\n...[stream truncated]..."
        return result


class SubprocessRunner(BaseExecutionRunner):
    """Host subprocess runner with environment sanitization and bounded streaming."""

    @property
    def name(self) -> str:
        return "subprocess"

    def is_available(self) -> bool:
        return True

    def execute(
        self,
        exec_target: Path,
        cli_args: list[Any],
        workspace: Path,
        stdin_text: Optional[str],
        timeout: int,
        max_output_bytes: int,
        cancellation_event: threading.Event,
    ) -> tuple[bool, str, dict[str, Any]]:
        cmd = [sys.executable, str(exec_target), *[str(arg) for arg in cli_args]]
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
            with tempfile.TemporaryFile(mode="w+b") as stdin_file:
                if stdin_text is not None:
                    stdin_file.write(stdin_text.encode("utf-8"))
                    stdin_file.seek(0)
                process = subprocess.Popen(
                    cmd,
                    cwd=str(workspace),
                    stdin=stdin_file if stdin_text is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                )
                stdout_capture = bytearray()
                stderr_capture = bytearray()
                stdout_size = [0]
                stderr_size = [0]

                def drain(stream: Any, capture: bytearray, total_size: list[int]) -> None:
                    while chunk := stream.read(8192):
                        total_size[0] += len(chunk)
                        remaining = max_output_bytes - len(capture)
                        if remaining > 0:
                            capture.extend(chunk[:remaining])
                    stream.close()

                stdout_thread = threading.Thread(
                    target=drain,
                    args=(process.stdout, stdout_capture, stdout_size),
                    daemon=True,
                )
                stderr_thread = threading.Thread(
                    target=drain,
                    args=(process.stderr, stderr_capture, stderr_size),
                    daemon=True,
                )
                stdout_thread.start()
                stderr_thread.start()

                timed_out = False
                cancelled = False
                deadline = start_time + timeout
                while process.poll() is None:
                    if cancellation_event.is_set():
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
                        cancellation_event.set()
                        process.kill()
                        process.wait()
                        break

                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                output_truncated = (
                    stdout_size[0] > max_output_bytes or stderr_size[0] > max_output_bytes
                )
                stdout = self.decode_capture(stdout_capture, stdout_size[0])
                stderr = self.decode_capture(stderr_capture, stderr_size[0])
                metadata = {
                    "runner": self.name,
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
                "runner": self.name,
                "returncode": -1,
                "duration_ms": round((time.perf_counter() - start_time) * 1000.0, 2),
                "error": str(exc),
            }


class DockerRunner(BaseExecutionRunner):
    """Sandboxed execution runner using Docker containers with bounded memory and disabled network."""

    def __init__(self, image: str = "python:3.11-slim", memory_limit: str = "512m", cpus: str = "1.0"):
        self.image = image
        self.memory_limit = memory_limit
        self.cpus = cpus
        self._available: Optional[bool] = None

    @property
    def name(self) -> str:
        return "docker"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        docker_bin = shutil.which("docker")
        if not docker_bin:
            self._available = False
            return False
        try:
            # Check if docker daemon responds
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3.0,
            )
            self._available = res.returncode == 0
        except Exception:
            self._available = False
        return self._available

    def execute(
        self,
        exec_target: Path,
        cli_args: list[Any],
        workspace: Path,
        stdin_text: Optional[str],
        timeout: int,
        max_output_bytes: int,
        cancellation_event: threading.Event,
    ) -> tuple[bool, str, dict[str, Any]]:
        if not self.is_available():
            return False, "Docker daemon is not available or not running.", {"runner": self.name}

        # Calculate path relative to workspace
        try:
            rel_path = exec_target.relative_to(workspace).as_posix()
        except ValueError:
            return False, f"Target '{exec_target}' is outside workspace '{workspace}'.", {"runner": self.name}

        # Docker run flags:
        # --rm: remove container upon exit
        # -i: keep stdin open
        # --network none: block outbound and inbound network access
        # -v <workspace>:/workspace: mount workspace into /workspace
        # -w /workspace: working directory inside container
        # --memory <limit>, --cpus <cpus>: limit resource consumption
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--memory",
            self.memory_limit,
            "--cpus",
            self.cpus,
            "-v",
            f"{workspace.resolve()}:/workspace",
            "-w",
            "/workspace",
            self.image,
            "python",
            rel_path,
            *[str(arg) for arg in cli_args],
        ]

        start_time = time.perf_counter()
        try:
            with tempfile.TemporaryFile(mode="w+b") as stdin_file:
                if stdin_text is not None:
                    stdin_file.write(stdin_text.encode("utf-8"))
                    stdin_file.seek(0)

                process = subprocess.Popen(
                    cmd,
                    cwd=str(workspace),
                    stdin=stdin_file if stdin_text is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout_capture = bytearray()
                stderr_capture = bytearray()
                stdout_size = [0]
                stderr_size = [0]

                def drain(stream: Any, capture: bytearray, total_size: list[int]) -> None:
                    while chunk := stream.read(8192):
                        total_size[0] += len(chunk)
                        remaining = max_output_bytes - len(capture)
                        if remaining > 0:
                            capture.extend(chunk[:remaining])
                    stream.close()

                stdout_thread = threading.Thread(
                    target=drain,
                    args=(process.stdout, stdout_capture, stdout_size),
                    daemon=True,
                )
                stderr_thread = threading.Thread(
                    target=drain,
                    args=(process.stderr, stderr_capture, stderr_size),
                    daemon=True,
                )
                stdout_thread.start()
                stderr_thread.start()

                timed_out = False
                cancelled = False
                deadline = start_time + timeout
                while process.poll() is None:
                    if cancellation_event.is_set():
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
                        cancellation_event.set()
                        process.kill()
                        process.wait()
                        break

                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                output_truncated = (
                    stdout_size[0] > max_output_bytes or stderr_size[0] > max_output_bytes
                )
                stdout = self.decode_capture(stdout_capture, stdout_size[0])
                stderr = self.decode_capture(stderr_capture, stderr_size[0])
                metadata = {
                    "runner": self.name,
                    "returncode": -1 if timed_out else process.returncode,
                    "duration_ms": duration_ms,
                    "stdout": stdout,
                    "stderr": stderr,
                    "script": exec_target.name,
                    "output_truncated": output_truncated,
                }
                if timed_out:
                    metadata["timeout"] = timeout
                    return False, f"Docker sandboxed execution timed out after {timeout} seconds.", metadata
                if cancelled:
                    metadata["cancelled"] = True
                    return False, "Docker execution cancelled by user.", metadata
                if process.returncode == 0:
                    return True, stdout or "(Sandboxed execution completed with exit code 0 and empty output)", metadata
                report = f"Sandboxed execution failed (exit code {process.returncode}):"
                if stderr:
                    report += f"\nSTDERR:\n{stderr}"
                if stdout:
                    report += f"\nSTDOUT:\n{stdout}"
                return False, report, metadata
        except Exception as exc:
            return False, f"Failed to spawn Docker container: {exc}", {
                "runner": self.name,
                "returncode": -1,
                "duration_ms": round((time.perf_counter() - start_time) * 1000.0, 2),
                "error": str(exc),
            }
