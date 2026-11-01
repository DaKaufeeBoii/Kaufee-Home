"""Standard JSON-RPC 2.0 stdio client for Model Context Protocol (MCP) servers."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any, Optional


class MCPClientError(Exception):
    """Raised when an MCP operation fails or server encounters an error."""
    pass


class MCPClient:
    """Manages connection and tool invocations with an external MCP server via stdio JSON-RPC."""

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 15.0,
    ):
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env
        self.timeout = timeout

        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self._is_initialized = False

    def start(self) -> None:
        """Spawn server process and complete MCP initialize handshake."""
        if self._process is not None:
            return

        cmd = [self.command] + self.args
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                encoding="utf-8",
                errors="replace",
                env=self.env,
            )
        except Exception as exc:
            raise MCPClientError(
                f"Failed to launch MCP server '{self.server_name}' using command '{self.command}': {exc}"
            ) from exc

        self._initialize()

    def _send_request(self, method: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request and return the result field."""
        if self._process is None or self._process.poll() is not None:
            raise MCPClientError(f"MCP server '{self.server_name}' process is not running.")

        with self._lock:
            self._request_id += 1
            req_id = self._request_id
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            }
            raw_msg = json.dumps(payload) + "\n"

            try:
                assert self._process.stdin is not None
                self._process.stdin.write(raw_msg)
                self._process.stdin.flush()
            except Exception as exc:
                raise MCPClientError(f"Failed to write to MCP server '{self.server_name}' stdin: {exc}") from exc

            # Read response with timeout
            start_time = time.time()
            while True:
                if time.time() - start_time > self.timeout:
                    raise MCPClientError(
                        f"Timed out waiting for response from MCP server '{self.server_name}' (method '{method}')"
                    )

                assert self._process.stdout is not None
                line = self._process.stdout.readline()
                if not line:
                    exit_code = self._process.poll()
                    if exit_code is not None:
                        stderr_out = ""
                        if self._process.stderr:
                            try:
                                stderr_out = self._process.stderr.read()
                            except Exception:
                                pass
                        raise MCPClientError(
                            f"MCP server '{self.server_name}' terminated unexpectedly with exit code {exit_code}. {stderr_out}"
                        )
                    time.sleep(0.01)
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Ignore notifications or responses for other IDs
                if data.get("id") == req_id:
                    if "error" in data:
                        err = data["error"]
                        err_msg = err.get("message", "Unknown error") if isinstance(err, dict) else str(err)
                        raise MCPClientError(f"MCP server error ({method}): {err_msg}")
                    return data.get("result", {})

    def _send_notification(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        """Send a one-way JSON-RPC notification."""
        if self._process is None or self._process.poll() is not None:
            return

        with self._lock:
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
            raw_msg = json.dumps(payload) + "\n"
            try:
                assert self._process.stdin is not None
                self._process.stdin.write(raw_msg)
                self._process.stdin.flush()
            except Exception:
                pass

    def _initialize(self) -> None:
        """Execute MCP initialize handshake protocol."""
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": False},
            },
            "clientInfo": {
                "name": "kaufee-home",
                "version": "0.3.0",
            },
        }
        res = self._send_request("initialize", init_params)
        self._is_initialized = True
        self._send_notification("notifications/initialized")

    def list_tools(self) -> list[dict[str, Any]]:
        """Query server for available tools via tools/list."""
        if not self._is_initialized:
            self.start()
        res = self._send_request("tools/list")
        return res.get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        """
        Invoke tool via tools/call.
        Returns:
            (success: bool, output_or_error: str, metadata: dict)
        """
        if not self._is_initialized:
            self.start()

        params = {
            "name": tool_name,
            "arguments": arguments,
        }
        try:
            res = self._send_request("tools/call", params)
        except MCPClientError as exc:
            return False, str(exc), {"server": self.server_name, "error": str(exc)}

        is_error = bool(res.get("isError", False))
        content_items = res.get("content", [])
        text_outputs: list[str] = []

        for item in content_items:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_outputs.append(item.get("text", ""))
                else:
                    text_outputs.append(str(item))
            else:
                text_outputs.append(str(item))

        full_output = "\n".join(text_outputs) if text_outputs else ("Tool executed successfully" if not is_error else "Tool failed")
        return not is_error, full_output, {"server": self.server_name, "is_mcp": True}

    def close(self) -> None:
        """Terminate server process and clean up resources."""
        with self._lock:
            if self._process is not None:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=2.0)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                finally:
                    self._process = None
                    self._is_initialized = False
