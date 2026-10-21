"""Workspace manager for safe path resolution, file backups, and diff tracking."""

from __future__ import annotations

import difflib
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
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
            self._write_manifest([])

    def _read_manifest(self) -> list[dict]:
        with open(self.manifest_path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ValueError("Backup manifest must contain a list of records")
        return data

    def _write_manifest(self, manifest: list[dict]) -> None:
        """Replace the manifest atomically so interruption cannot leave partial JSON."""
        fd, temporary_name = tempfile.mkstemp(prefix="manifest_", suffix=".tmp", dir=self.backup_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(manifest, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.manifest_path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def record_backup(self, record: dict) -> None:
        manifest = self._read_manifest()
        manifest.append(record)
        self._write_manifest(manifest)

    @staticmethod
    def atomic_write(destination: Path, content: bytes) -> None:
        """Write bytes beside the destination and atomically replace the file."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        mode = None
        try:
            mode = stat.S_IMODE(destination.stat().st_mode)
        except FileNotFoundError:
            pass
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if mode is not None:
                os.chmod(temporary_name, mode)
            os.replace(temporary_name, destination)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def atomic_copy(source: Path, destination: Path) -> None:
        """Copy a file to a sibling temporary file, then replace destination."""
        WorkspaceManager.atomic_write(destination, source.read_bytes())

    def backup_path(self, target_path: Path, reason: str) -> Optional[str]:
        """Snapshot a file or directory and record it before its caller mutates it."""
        target_path = self.resolve_path(target_path, must_exist=True)
        if target_path.is_symlink():
            return None
        if not target_path.is_file() and not target_path.is_dir():
            return None

        timestamp = time.time_ns()
        backup_id = f"{timestamp}_{target_path.name or 'workspace'}"
        backup_item = self.backup_dir / backup_id
        is_directory = target_path.is_dir()
        if is_directory:
            shutil.copytree(target_path, backup_item, symlinks=True)
        else:
            shutil.copy2(target_path, backup_item)
        record = {
            "backup_id": backup_id,
            "original_path": target_path.relative_to(self.workspace_root).as_posix(),
            "timestamp": timestamp,
            "reason": reason,
            "backup_file": str(backup_item),
            "is_directory": is_directory,
        }
        try:
            self.record_backup(record)
        except Exception:
            if is_directory:
                shutil.rmtree(backup_item, ignore_errors=True)
            else:
                backup_item.unlink(missing_ok=True)
            raise
        return backup_id

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

        return self.backup_path(target_path, reason)

    def restore_latest_backup(self, target_rel_path: str) -> tuple[bool, str]:
        """Restore file from the latest available backup in manifest."""
        try:
            manifest = self._read_manifest()
        except Exception as exc:
            return False, f"Could not read backup manifest: {exc}"

        safe_target = self.resolve_path(target_rel_path)
        normalized_target = safe_target.relative_to(self.workspace_root).as_posix()
        matches = [m for m in manifest if m.get("original_path", "").replace("\\", "/") == normalized_target]
        if not matches:
            return False, f"No backups found for '{target_rel_path}'"

        latest = sorted(matches, key=lambda m: m["timestamp"], reverse=True)[0]
        if latest.get("reason") == "move_file":
            source = self.resolve_path(target_rel_path)
            destination = self.resolve_path(latest.get("destination_path", ""), must_exist=True)
            if source.exists():
                return False, f"Cannot undo move because source path '{target_rel_path}' already exists"
            destination_backup_id = latest.get("destination_backup_id")
            destination_record = None
            backup_file = None
            if destination_backup_id:
                destination_record = next(
                    (record for record in manifest if record.get("backup_id") == destination_backup_id),
                    None,
                )
                if destination_record is None:
                    return False, "Cannot undo move: overwritten destination backup record is missing"
                backup_file = Path(destination_record.get("backup_file", ""))
                if not backup_file.is_file():
                    return False, "Cannot undo move: overwritten destination backup file is missing"
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(source))
            if backup_file is not None:
                self.atomic_copy(backup_file, destination)
            return True, f"Undid move from '{target_rel_path}' to '{latest['destination_path']}'"

        backup_file = Path(latest["backup_file"])
        is_directory = latest.get("is_directory", False)
        if is_directory and not backup_file.is_dir():
            return False, f"Directory backup '{backup_file}' missing from disk"
        if not is_directory and not backup_file.is_file():
            return False, f"Backup file '{backup_file}' missing from disk"

        destination = safe_target
        destination.parent.mkdir(parents=True, exist_ok=True)
        if is_directory:
            if destination.exists():
                if not destination.is_dir():
                    return False, f"Cannot restore directory over non-directory '{target_rel_path}'"
            stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.restore-", dir=destination.parent))
            stage.rmdir()
            displaced = destination.parent / f".{destination.name}.previous-{uuid.uuid4().hex}"
            try:
                shutil.copytree(backup_file, stage, symlinks=True)
                if destination.exists():
                    os.replace(destination, displaced)
                try:
                    os.replace(stage, destination)
                except Exception:
                    if displaced.exists():
                        os.replace(displaced, destination)
                    raise
                if displaced.exists():
                    shutil.rmtree(displaced)
            except Exception as exc:
                return False, f"Could not restore directory '{target_rel_path}': {exc}"
            finally:
                if stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)
        else:
            if destination.is_dir():
                return False, f"Cannot restore file over directory '{target_rel_path}'"
            self.atomic_copy(backup_file, destination)
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
