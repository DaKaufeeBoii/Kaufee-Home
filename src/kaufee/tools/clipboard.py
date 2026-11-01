"""Clipboard interaction tools with automated secret redaction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyperclip

from kaufee.safety.redactor import redact_sensitive_text
from kaufee.tools.base import BaseTool


class ReadClipboardTool(BaseTool):
    """Read textual content from the system clipboard with secret redaction."""

    name = "read_clipboard"
    description = "Read text currently stored on the system clipboard with automatic secret redaction."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        try:
            raw = pyperclip.paste()
            if not raw:
                return True, "(Clipboard is empty)", {"length": 0}
            sanitized = redact_sensitive_text(raw)
            return True, sanitized, {"length": len(sanitized), "redacted": sanitized != raw}
        except Exception as exc:
            return False, f"Failed to read clipboard: {exc}", {"error": str(exc)}


class WriteClipboardTool(BaseTool):
    """Copy textual content to the system clipboard."""

    name = "write_clipboard"
    description = "Copy text content to the system clipboard."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Text to copy to clipboard."},
            },
            "required": ["content"],
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        content = arguments.get("content")
        if content is None:
            return False, "Argument 'content' is required.", {}
        try:
            pyperclip.copy(str(content))
            return True, f"Copied {len(str(content))} characters to clipboard.", {"length": len(str(content))}
        except Exception as exc:
            return False, f"Failed to write to clipboard: {exc}", {"error": str(exc)}
