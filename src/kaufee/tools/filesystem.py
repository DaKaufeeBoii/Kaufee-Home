"""Filesystem tools for safe workspace manipulation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from kaufee.safety.permissions import is_path_safe_and_within_workspace
from kaufee.tools.base import BaseTool
from kaufee.tools.workspace import WorkspaceManager


class ListFilesTool(BaseTool):
    """Tool to list directory contents within the workspace."""

    name = "list_files"
    description = "List files and directories in the workspace. Returns names, sizes, and types."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Relative directory path inside workspace. Defaults to root ('.').",
                    "default": ".",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list subdirectories recursively.",
                    "default": False,
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        dir_arg = arguments.get("directory", ".")
        recursive = arguments.get("recursive", False)

        is_safe, msg, target = is_path_safe_and_within_workspace(dir_arg, workspace_root, must_exist=True)
        if not is_safe or target is None:
            return False, msg, {}

        if not target.is_dir():
            return False, f"Target '{dir_arg}' is a file, not a directory.", {}

        items: list[str] = []
        file_count = 0
        dir_count = 0

        if recursive:
            iterator = target.rglob("*")
        else:
            iterator = target.iterdir()

        for entry in sorted(iterator):
            # Skip internal .kaufee folder
            try:
                rel = entry.relative_to(workspace_root)
            except ValueError:
                continue
            if ".kaufee" in rel.parts or ".git" in rel.parts:
                continue

            if entry.is_dir():
                dir_count += 1
                items.append(f"[DIR]  {rel}")
            else:
                file_count += 1
                size = entry.stat().st_size
                items.append(f"[FILE] {rel} ({size} bytes)")

        if not items:
            return True, "Directory is empty.", {"file_count": 0, "dir_count": 0}

        summary = f"Found {file_count} file(s), {dir_count} folder(s):\n" + "\n".join(items)
        return True, summary, {"file_count": file_count, "dir_count": dir_count}


class ReadFileTool(BaseTool):
    """Tool to read the contents of a workspace file."""

    name = "read_file"
    description = "Read text content of a file within the workspace."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of file inside workspace to read.",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Maximum bytes to read (prevents excessive output).",
                    "default": 50000,
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        file_path_arg = arguments.get("path")
        if not file_path_arg:
            return False, "Argument 'path' is required.", {}

        max_bytes = int(arguments.get("max_bytes", 50000))
        is_safe, msg, target = is_path_safe_and_within_workspace(file_path_arg, workspace_root, must_exist=True)
        if not is_safe or target is None:
            return False, msg, {}

        if not target.is_file():
            return False, f"Target '{file_path_arg}' is not a file.", {}

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)

            line_count = len(content.splitlines())
            return True, content, {"path": str(target.relative_to(workspace_root)), "lines": line_count}
        except Exception as exc:
            return False, f"Failed to read file: {exc}", {}


class WriteFileTool(BaseTool):
    """Tool to create or overwrite a file within the workspace with backup."""

    name = "write_file"
    description = "Create or overwrite a file with provided content. Automatically creates parent directories if needed and backups existing files."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of file to create or overwrite.",
                },
                "content": {
                    "type": "string",
                    "description": "Full text content to write.",
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        file_path_arg = arguments.get("path")
        content = arguments.get("content", "")

        if not file_path_arg:
            return False, "Argument 'path' is required.", {}

        is_safe, msg, target = is_path_safe_and_within_workspace(file_path_arg, workspace_root, must_exist=False)
        if not is_safe or target is None:
            return False, msg, {}

        ws_mgr = WorkspaceManager(workspace_root)
        backup_id = None
        old_content = ""

        if target.exists():
            if target.is_dir():
                return False, f"Path '{file_path_arg}' points to an existing directory.", {}
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
            except Exception:
                old_content = ""
            backup_id = ws_mgr.backup_file(target, reason="write_file_overwrite")

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)

        diff_summary = ""
        if old_content:
            diff = ws_mgr.generate_diff(old_content, content, target.name)
            diff_summary = f"\nDiff:\n{diff}" if diff else " (Content unchanged)"

        msg = f"Successfully wrote {len(content)} characters to '{target.relative_to(workspace_root)}'.{diff_summary}"
        return True, msg, {
            "path": str(target.relative_to(workspace_root)),
            "bytes_written": len(content.encode("utf-8")),
            "backup_id": backup_id,
        }


class EditFileTool(BaseTool):
    """Tool to perform surgical search-and-replace edits on a workspace file."""

    name = "edit_file"
    description = "Perform a targeted search-and-replace edit on an existing file. Automatically creates a backup."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["path", "target_content", "replacement_content"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of file to edit.",
                },
                "target_content": {
                    "type": "string",
                    "description": "Exact text snippet to find and replace.",
                },
                "replacement_content": {
                    "type": "string",
                    "description": "Text to replace target_content with.",
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        file_path_arg = arguments.get("path")
        target_str = arguments.get("target_content")
        replacement_str = arguments.get("replacement_content", "")

        if not file_path_arg or target_str is None:
            return False, "Arguments 'path' and 'target_content' are required.", {}

        is_safe, msg, target = is_path_safe_and_within_workspace(file_path_arg, workspace_root, must_exist=True)
        if not is_safe or target is None:
            return False, msg, {}

        if not target.is_file():
            return False, f"Target '{file_path_arg}' is not a file.", {}

        with open(target, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()

        count = original.count(target_str)
        if count == 0:
            return False, f"Target content not found in '{file_path_arg}'. Edit aborted.", {}
        if count > 1:
            return (
                False,
                f"Target content occurs {count} times in '{file_path_arg}'. Please specify a unique snippet.",
                {},
            )

        ws_mgr = WorkspaceManager(workspace_root)
        backup_id = ws_mgr.backup_file(target, reason="edit_file")

        updated = original.replace(target_str, replacement_str, 1)
        with open(target, "w", encoding="utf-8") as f:
            f.write(updated)

        diff = ws_mgr.generate_diff(original, updated, target.name)
        msg = f"Successfully edited '{target.relative_to(workspace_root)}'.\nDiff:\n{diff}"
        return True, msg, {
            "path": str(target.relative_to(workspace_root)),
            "backup_id": backup_id,
        }


class MoveFileTool(BaseTool):
    """Tool to move or rename files or directories within the workspace."""

    name = "move_file"
    description = "Move or rename a file or directory within the workspace."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["source_path", "destination_path"],
            "properties": {
                "source_path": {
                    "type": "string",
                    "description": "Source path relative to workspace.",
                },
                "destination_path": {
                    "type": "string",
                    "description": "Destination path relative to workspace.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether to overwrite destination if it exists.",
                    "default": False,
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        src_arg = arguments.get("source_path")
        dst_arg = arguments.get("destination_path")
        overwrite = arguments.get("overwrite", False)

        if not src_arg or not dst_arg:
            return False, "Both 'source_path' and 'destination_path' are required.", {}

        is_safe_src, msg_src, src = is_path_safe_and_within_workspace(src_arg, workspace_root, must_exist=True)
        if not is_safe_src or src is None:
            return False, msg_src, {}

        is_safe_dst, msg_dst, dst = is_path_safe_and_within_workspace(dst_arg, workspace_root, must_exist=False)
        if not is_safe_dst or dst is None:
            return False, msg_dst, {}

        if dst.exists() and not overwrite:
            return False, f"Destination path '{dst_arg}' already exists and overwrite is false.", {}

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        return True, f"Moved '{src.relative_to(workspace_root)}' to '{dst.relative_to(workspace_root)}'.", {
            "source": str(src.relative_to(workspace_root)),
            "destination": str(dst.relative_to(workspace_root)),
        }


class DeleteFileTool(BaseTool):
    """Tool to delete a file or directory after making an undo backup."""

    name = "delete_file"
    description = "Delete a file or directory from the workspace. Automatically creates a backup for safety."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of file or directory to delete.",
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        file_path_arg = arguments.get("path")
        if not file_path_arg:
            return False, "Argument 'path' is required.", {}

        is_safe, msg, target = is_path_safe_and_within_workspace(file_path_arg, workspace_root, must_exist=True)
        if not is_safe or target is None:
            return False, msg, {}

        ws_mgr = WorkspaceManager(workspace_root)
        backup_id = None

        if target.is_file():
            backup_id = ws_mgr.backup_file(target, reason="delete_file")
            target.unlink()
            return True, f"File '{target.relative_to(workspace_root)}' deleted (Backup ID: {backup_id}).", {
                "backup_id": backup_id,
            }
        elif target.is_dir():
            shutil.rmtree(target)
            return True, f"Directory '{target.relative_to(workspace_root)}' deleted.", {}

        return False, f"Target '{file_path_arg}' not found.", {}


class UndoFileTool(BaseTool):
    """Tool to revert a file to its latest backup state."""

    name = "undo_file"
    description = "Revert a file in the workspace to its latest backup snapshot."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to revert.",
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        file_path_arg = arguments.get("path")
        if not file_path_arg:
            return False, "Argument 'path' is required.", {}

        ws_mgr = WorkspaceManager(workspace_root)
        success, msg = ws_mgr.restore_latest_backup(file_path_arg)
        return success, msg, {}
