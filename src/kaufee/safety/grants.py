"""Session-level temporary scoped permissions and security grants."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScopedGrant:
    """Represents a temporary permission grant."""
    scope: str  # e.g., "workspace", "browser"
    expires_at: float
    description: str

    @property
    def is_active(self) -> bool:
        return time.time() < self.expires_at

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.expires_at - time.time())


def parse_duration_seconds(duration_str: str) -> float:
    """
    Parse a human-readable duration string into seconds.
    Examples: '15m' -> 900.0, '1h' -> 3600.0, '30s' -> 30.0, '45' -> 45.0.
    """
    if not duration_str:
        return 0.0
    text = duration_str.strip().lower()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([smhd])?$", text)
    if not match:
        raise ValueError(f"Invalid duration format: '{duration_str}'. Use format like '15m', '1h', '30s'.")
    value, unit = match.groups()
    num = float(value)
    multipliers = {
        "s": 1.0,
        "m": 60.0,
        "h": 3600.0,
        "d": 86400.0,
    }
    return num * multipliers.get(unit or "s", 1.0)


class ScopedGrantManager:
    """Tracks and evaluates temporary permission grants to reduce approval friction safely."""

    def __init__(self):
        self._grants: dict[str, ScopedGrant] = {}

    def grant(self, scope: str, duration: str | float, description: str = "") -> ScopedGrant:
        """Create or extend a temporary scoped permission grant."""
        duration_sec = parse_duration_seconds(duration) if isinstance(duration, str) else float(duration)
        expires_at = time.time() + duration_sec
        grant = ScopedGrant(
            scope=scope.lower().strip(),
            expires_at=expires_at,
            description=description or f"Temporary {scope} grant for {duration_sec:.0f}s",
        )
        self._grants[grant.scope] = grant
        return grant

    def has_active_grant(self, scope: str) -> bool:
        """Check if an active, unexpired grant exists for the given scope."""
        scope_key = scope.lower().strip()
        grant = self._grants.get(scope_key)
        if grant is None:
            return False
        if not grant.is_active:
            # Clean up expired grant
            del self._grants[scope_key]
            return False
        return True

    def revoke(self, scope: str) -> bool:
        """Revoke an active grant immediately."""
        scope_key = scope.lower().strip()
        if scope_key in self._grants:
            del self._grants[scope_key]
            return True
        return False

    def list_active_grants(self) -> list[ScopedGrant]:
        """Return list of all currently active grants."""
        active = []
        expired = []
        for key, grant in self._grants.items():
            if grant.is_active:
                active.append(grant)
            else:
                expired.append(key)
        for key in expired:
            del self._grants[key]
        return active
