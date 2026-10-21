"""Workspace manager for safe path resolution, file backups, and diff tracking."""

from __future__ import annotations

import difflib
import json
import shutil
import time
from pathlib import Path
from typing import Optional
from kaufee.safety.permissions import is_path_safe_and_within_workspace


class WorkspaceManager:
    """Manages workspace paths, backups, and change history."""

    def __init__(self, workspace_root: Path, backup_dir: Optional[Path] = None):
        self.workspace_root = workspace_root.resolve()
        self.backup_dir = (backup_dir or (self.workspace_root / ".kaufee" / "backups")).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.backup_dir / "backups_manifest.json"
        self._ensure_manifest()

    def _ensure_manifest(self) -> None:
        if not self.manifest_path.exists():
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def resolve_path(self, target: str | Path, must_exist: bool = False) -> Path:
        """Resolve path and verify it is strictly inside workspace."""
        is_safe, msg, resolved = is_path_safe_and_within_workspace(
            target, self.workspace_root, must_exist=must_exist
        )
        if not is_safe or resolved is None:
            raise PermissionError(msg)
        return resolved

    def backup_file(self, target_path: Path, reason: str = "change") -> Optional[str]:
        """Create a backup of a file before modifying or deleting it."""
        if not target_path.is_file():
            return None

        timestamp = int(time.time() * 1000)
        rel_path = target_path.relative_to(self.workspace_root)
        clean_name = str(rel_path).replace("\\", "_").replace("/", "_")
        backup_filename = f"{timestamp}_{clean_name}"
        backup_file_path = self.backup_dir / backup_filename

        shutil.copy2(target_path, backup_file_path)

        record = {
            "backup_id": backup_filename,
            "original_path": str(rel_path),
            "timestamp": timestamp,
            "reason": reason,
            "backup_file": str(backup_file_path),
        }

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest.append(record)
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass

        return backup_filename

    def restore_latest_backup(self, target_rel_path: str) -> tuple[bool, str]:
        """Restore file from the latest available backup in manifest."""
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as exc:
            return False, f"Could not read backup manifest: {exc}"

        matches = [m for m in manifest if m["original_path"] == target_rel_path]
        if not matches:
            return False, f"No backups found for '{target_rel_path}'"

        latest = sorted(matches, key=lambda m: m["timestamp"], reverse=True)[0]
        backup_file = Path(latest["backup_file"])
        if not backup_file.is_file():
            return False, f"Backup file '{backup_file}' missing from disk"

        destination = self.resolve_path(target_rel_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, destination)
        return True, f"Restored '{target_rel_path}' from backup {latest['backup_id']}"

    @staticmethod
    def generate_diff(old_content: str, new_content: str, file_name: str = "file") -> str:
        """Generate unified diff string between old and new content."""
        diff_lines = list(
            difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{file_name}",
                tofile=f"b/{file_name}",
            )
        )
        return "".join(diff_lines)
