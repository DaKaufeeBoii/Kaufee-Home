"""Permission definitions and path validation rules for Kaufee-Home."""

from __future__ import annotations

import os
from pathlib import Path
from kaufee.state.models import RiskLevel


FORBIDDEN_PATTERNS = {
    ".git",
    ".env",
    "id_rsa",
    "id_ed25519",
    ".aws",
    ".ssh",
    "passwd",
    "shadow",
    "windows\\system32",
    "system32",
}


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

        # Check for sensitive path substrings
        resolved_str_lower = str(resolved).lower()
        for forbidden in FORBIDDEN_PATTERNS:
            if forbidden in resolved_str_lower.split(os.sep):
                return False, f"Access blocked to protected file or directory '{forbidden}'", None

        if must_exist and not resolved.exists():
            return False, f"Target path does not exist: '{target_path}'", None

        return True, "Path is within permitted workspace boundary.", resolved

    except Exception as exc:
        return False, f"Path validation error for '{target_path}': {exc}", None
