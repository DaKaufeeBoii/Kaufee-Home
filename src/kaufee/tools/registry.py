"""Tool registry for registering, discovering, and executing tools."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Optional
from kaufee.config import KaufeeConfig
from kaufee.state.models import ToolCall, ToolResult
from kaufee.tools.base import BaseTool
from kaufee.tools.browser import (
    BrowserClickTool,
    BrowserDownloadTool,
    BrowserFillTool,
    BrowserOpenTool,
    BrowserScrapeTool,
)
from kaufee.tools.clipboard import ReadClipboardTool, WriteClipboardTool
from kaufee.tools.filesystem import (
    CreateDirectoryTool,
    DeleteFileTool,
    EditFileTool,
    ListFilesTool,
    MoveFileTool,
    ReadFileTool,
    UndoFileTool,
    WriteFileTool,
)
from kaufee.tools.python_runner import PythonRunnerTool
from kaufee.tools.system import DesktopNotificationTool, LaunchApplicationTool, ListProcessesTool


class ToolRegistry:
    """Registry maintaining available tools and schemas."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name.lower()] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieve a tool by name."""
        return self._tools.get(name.lower().strip())

    def list_tools(self) -> list[BaseTool]:
        """Return list of all registered tool instances."""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return schema list suitable for LLM prompt or function calling."""
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            })
        return schemas

    def execute(
        self,
        action: ToolCall,
        workspace_root: Path,
        cancellation_event: threading.Event | None = None,
    ) -> ToolResult:
        """Execute a tool call and return structured ToolResult."""
        tool = self.get(action.tool_name)
        if not tool:
            return ToolResult(
                call_id=action.call_id,
                tool_name=action.tool_name,
                success=False,
                output="",
                error=f"Tool '{action.tool_name}' is not registered.",
            )
        if isinstance(tool, PythonRunnerTool) and cancellation_event is not None:
            tool.cancellation_event = cancellation_event
        return tool.execute(action.arguments, workspace_root, call_id=action.call_id)

    @classmethod
    def create_default(
        cls,
        config: Optional[KaufeeConfig] = None,
        workspace_root: Optional[Path] = None,
    ) -> ToolRegistry:
        """Instantiate default registry with all core filesystem, runner, and discovered MCP tools."""
        registry = cls()
        timeout = config.step_timeout if config else 15
        max_bytes = config.max_output_bytes if config else 50000

        registry.register(ListFilesTool())
        registry.register(CreateDirectoryTool())
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        registry.register(EditFileTool())
        registry.register(MoveFileTool())
        registry.register(DeleteFileTool())
        registry.register(UndoFileTool())
        registry.register(BrowserOpenTool(timeout_seconds=timeout))
        registry.register(BrowserScrapeTool(timeout_seconds=timeout))
        registry.register(BrowserDownloadTool(timeout_seconds=timeout * 2))
        registry.register(BrowserClickTool(timeout_seconds=timeout))
        registry.register(BrowserFillTool(timeout_seconds=timeout))
        registry.register(LaunchApplicationTool())
        registry.register(ListProcessesTool())
        registry.register(DesktopNotificationTool())
        registry.register(ReadClipboardTool())
        registry.register(WriteClipboardTool())
        runner_type = config.runner_type if config else "auto"
        registry.register(
            PythonRunnerTool(
                default_timeout=timeout,
                max_output_bytes=max_bytes,
                runner_type=runner_type,
            )
        )

        # Discover MCP servers if configured
        if workspace_root:
            from kaufee.mcp.manager import MCPManager
            mcp_mgr = MCPManager(workspace_root=workspace_root)
            mcp_mgr.discover_and_register_tools(registry)

        return registry
