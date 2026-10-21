"""Permission definitions and path validation rules for Kaufee-Home."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


FORBIDDEN_PATTERNS = {
    ".kaufee",
    ".git",
    ".env",
    "id_rsa",
    "id_ed25519",
    ".aws",
    ".ssh",
    "passwd",
    "shadow",
    "system32",
}


def _is_protected_path(path: Path) -> bool:
    """Match protected path components independently of OS path separators."""
    for component in path.parts:
        name = component.casefold()
        if name in FORBIDDEN_PATTERNS:
            return True
        # Protect dotenv files (including .env.local) and common SSH key names.
        if name.startswith(".env.") or name in {"authorized_keys", "known_hosts"}:
            return True
    return False


def is_path_safe_and_within_workspace(
    target_path: Path | str,
    workspace_root: Path,
    must_exist: bool = False,
) -> tuple[bool, str, Optional[Path]]:
    """
    Validate that target_path strictly resolves within workspace_root.
    Prevents path traversal, symlink escapes, and access to system-level/forbidden locations.
    """
    try:
        ws_canonical = workspace_root.resolve()
        raw_path = Path(target_path)

        # If path is relative, resolve it relative to workspace_root
        if not raw_path.is_absolute():
            resolved = (ws_canonical / raw_path).resolve()
        else:
            resolved = raw_path.resolve()

        # Check if resolved path is within workspace_root
        try:
            resolved.relative_to(ws_canonical)
        except ValueError:
            return False, f"Path traversal blocked: '{target_path}' resolves outside workspace '{ws_canonical}'", None

        # Reject symlinks in any existing component. Resolving first prevents
        # escapes, while this lexical walk also rejects internal symlinks whose
        # target happens to remain inside the workspace. This narrows (but does
        # not eliminate) races with concurrent filesystem changes.
        candidate = raw_path if raw_path.is_absolute() else ws_canonical / raw_path
        try:
            relative = candidate.absolute().relative_to(ws_canonical)
        except ValueError:
            return False, f"Path traversal blocked: '{target_path}' is outside workspace", None
        current = ws_canonical
        for component in relative.parts:
            if component in ("", "."):
                continue
            if component == "..":
                return False, f"Path traversal blocked: '{target_path}' contains parent traversal", None
            current = current / component
            try:
                if current.is_symlink():
                    return False, f"Access blocked through symbolic link '{current}'", None
            except OSError as exc:
                return False, f"Path validation error for '{target_path}': {exc}", None

        # Check both the user-supplied spelling and resolved path. This catches
        # protected names even when the target does not exist yet.
        if _is_protected_path(raw_path) or _is_protected_path(resolved):
            return False, f"Access blocked to protected path '{target_path}'", None

        if must_exist and not resolved.exists():
            return False, f"Target path does not exist: '{target_path}'", None

        return True, "Path is within permitted workspace boundary.", resolved

    except Exception as exc:
        return False, f"Path validation error for '{target_path}': {exc}", None
