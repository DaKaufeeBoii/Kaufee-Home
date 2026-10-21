"""Base class and interface for all Kaufee tools."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from kaufee.state.models import ToolResult


class BaseTool(ABC):
    """Abstract base class for all registered tools."""

    name: str = ""
    description: str = ""

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """JSON schema describing the required and optional arguments."""
        pass

    @abstractmethod
    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        """
        Execute tool logic.
        Returns:
            (success: bool, output_or_error_message: str, metadata: dict)
        """
        pass

    def execute(self, arguments: dict[str, Any], workspace_root: Path, call_id: str = "") -> ToolResult:
        """Standard execution wrapper capturing timing and exceptions."""
        start_time = time.perf_counter()
        try:
            success, output, metadata = self.run(arguments, workspace_root)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                success=success,
                output=output if success else "",
                error=output if not success else None,
                execution_time_ms=round(elapsed_ms, 2),
                metadata=metadata,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                call_id=call_id,
                tool_name=self.name,
                success=False,
                output="",
                error=f"Tool exception in '{self.name}': {str(exc)}",
                execution_time_ms=round(elapsed_ms, 2),
                metadata={"exception_type": type(exc).__name__},
            )
