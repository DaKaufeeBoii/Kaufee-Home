"""MCP Server Manager and Proxy Tool Integration for Kaufee-Home."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from kaufee.mcp.client import MCPClient, MCPClientError
from kaufee.safety.redactor import redact_data
from kaufee.tools.base import BaseTool
from kaufee.tools.registry import ToolRegistry


class MCPProxyTool(BaseTool):
    """Wraps an external MCP server tool into a native Kaufee BaseTool."""

    def __init__(
        self,
        server_name: str,
        mcp_tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        client: MCPClient,
    ):
        self.server_name = server_name
        self.mcp_tool_name = mcp_tool_name
        self.name = f"mcp__{server_name}__{mcp_tool_name}"
        self.description = f"[MCP: {server_name}] {description}"
        self._schema = input_schema or {"type": "object", "properties": {}}
        self._client = client

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return self._schema

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        # Execute tool via client
        success, output, meta = self._client.call_tool(self.mcp_tool_name, arguments)
        meta["server_name"] = self.server_name
        meta["mcp_tool"] = self.mcp_tool_name
        return success, output, meta


class MCPManager:
    """Discovers, initializes, and manages external Model Context Protocol (MCP) servers."""

    def __init__(self, workspace_root: Path | None = None, config_path: Path | None = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.config_path = config_path or (self.workspace_root / ".kaufee" / "mcp_servers.json")
        self.clients: dict[str, MCPClient] = {}
        self.proxy_tools: list[MCPProxyTool] = []

    def load_server_definitions(self) -> dict[str, Any]:
        """Load MCP server definitions from json configuration."""
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("mcpServers", {})
        except Exception:
            return {}

    def register_server(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> MCPClient:
        """Register and start an MCP server client."""
        client = MCPClient(
            server_name=name,
            command=command,
            args=args or [],
            env=env,
            timeout=timeout,
        )
        self.clients[name] = client
        return client

    def discover_and_register_tools(self, registry: ToolRegistry) -> int:
        """
        Connect to all configured servers, discover tools, and register proxy tools into ToolRegistry.
        Returns the number of MCP tools registered.
        """
        servers = self.load_server_definitions()
        for name, cfg in servers.items():
            command = cfg.get("command")
            if not command:
                continue
            args = cfg.get("args", [])
            env = cfg.get("env")
            client = self.register_server(name, command, args, env)
            try:
                client.start()
                tool_list = client.list_tools()
                for tool_meta in tool_list:
                    tool_name = tool_meta.get("name")
                    if not tool_name:
                        continue
                    proxy = MCPProxyTool(
                        server_name=name,
                        mcp_tool_name=tool_name,
                        description=tool_meta.get("description", ""),
                        input_schema=tool_meta.get("inputSchema", {}),
                        client=client,
                    )
                    self.proxy_tools.append(proxy)
                    registry.register(proxy)
            except Exception:
                # If an external server fails to launch, continue cleanly without breaking other tools
                continue

        return len(self.proxy_tools)

    def close_all(self) -> None:
        """Close all active MCP client processes."""
        for client in self.clients.values():
            try:
                client.close()
            except Exception:
                pass
        self.clients.clear()
        self.proxy_tools.clear()
