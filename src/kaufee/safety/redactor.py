"""Sensitive data redactor to uphold Privacy & Security principles."""

from __future__ import annotations

import re
from typing import Any

# Regular expression patterns for common sensitive tokens, keys, and PII
SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Private keys
    (
        "[REDACTED_PRIVATE_KEY]",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            re.IGNORECASE,
        ),
    ),
    # OpenAI API Keys
    ("[REDACTED_API_KEY]", re.compile(r"\bsk-[a-zA-Z0-9]{20,T3BlbkFJ[a-zA-Z0-9]{20,}\b|\bsk-proj-[a-zA-Z0-9_-]{20,}\b|\bsk-[a-zA-Z0-9]{32,}\b")),
    # GitHub Tokens
    ("[REDACTED_GITHUB_TOKEN]", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
    # AWS Access Key ID
    ("[REDACTED_AWS_KEY]", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Bearer tokens
    (
        r"Bearer [REDACTED_TOKEN]",
        re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{16,}\b"),
    ),
    # JWT tokens
    (
        "[REDACTED_JWT]",
        re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b"),
    ),
    # Key-value secret assignments: password=..., api_key=..., secret is...
    (
        r"\g<1>[REDACTED_SECRET]\g<3>",
        re.compile(
            r"""(?i)([\"']?(?:password|passwd|secret|api[_-]?key|token|auth[_-]?token)[\"']?(?:\s*[:=]\s*|\s+is\s+)[\"']?)([^\"'\s,;]{4,})([\"']?)"""
        ),
    ),
    # Credit card numbers (Luhn candidate regex)
    (
        "[REDACTED_CARD]",
        re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
    ),
    # Social Security Numbers (US format)
    (
        "[REDACTED_SSN]",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
]


SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)^(?:password|passwd|secret|api[_-]?key|token|auth[_-]?token|private[_-]?key|secret_key)$"
)


def redact_sensitive_text(text: str) -> str:
    """Scan and redact sensitive credentials, tokens, and secrets from text."""
    if not text or not isinstance(text, str):
        return text

    redacted = text
    for placeholder, pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(placeholder, redacted)
    return redacted


def redact_data(data: Any) -> Any:
    """Recursively redact sensitive text within nested structures (dicts, lists, primitives)."""
    if isinstance(data, str):
        return redact_sensitive_text(data)
    elif isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if isinstance(k, str) and SENSITIVE_KEY_PATTERN.match(k):
                result[k] = "[REDACTED_SECRET]"
            else:
                result[k] = redact_data(v)
        return result
    elif isinstance(data, list):
        return [redact_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(redact_data(item) for item in data)
    elif isinstance(data, set):
        return {redact_data(item) for item in data}
    return data
