"""Guardrails module to detect prompt injections and malicious inputs."""

from __future__ import annotations

import re
from typing import NamedTuple, Optional
from kaufee.safety.principles import ResponsibleAIPrinciple


class GuardrailResult(NamedTuple):
    """Result of a guardrail safety scan."""

    is_safe: bool
    reason: str
    principle: ResponsibleAIPrinciple
    matched_pattern: Optional[str] = None


# Heuristic patterns for direct and indirect prompt injection attempts
PROMPT_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "Instruction override attempt",
        re.compile(
            r"(?i)\b(?:ignore|disregard|forget|bypass)\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions|prompts|rules|commands|constraints)\b"
        ),
    ),
    (
        "System prompt override attempt",
        re.compile(
            r"(?i)\b(?:you\s+are\s+now|act\s+as)\s+(?:unrestricted|in\s+god\s+mode|dan|jailbroken|unfiltered)\b"
        ),
    ),
    (
        "Administrative override directive",
        re.compile(
            r"(?i)\b(?:system\s+override|admin\s+override|override\s+security\s+policy|disable\s+safety)\b"
        ),
    ),
    (
        "Credential exfiltration directive",
        re.compile(
            r"(?i)\b(?:exfiltrate|dump|leak|steal|send\s+to\s+http)\b.*\b(?:credentials|keys|tokens|passwords|secrets|id_rsa)\b"
        ),
    ),
]


class PromptInjectionGuard:
    """Evaluates incoming goals and tool outputs for adversarial injections and safety violations."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def check_input(self, text: str) -> GuardrailResult:
        """Scan input text (user goal or external file content) for prompt injection patterns."""
        if not self.enabled or not text:
            return GuardrailResult(
                is_safe=True,
                reason="Guardrail passed.",
                principle=ResponsibleAIPrinciple.PRIVACY_AND_SECURITY,
            )

        for label, pattern in PROMPT_INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_str = match.group(0)
                return GuardrailResult(
                    is_safe=False,
                    reason=(
                        f"Safety Guardrail Blocked: {label} detected ('{matched_str}'). "
                        "Agentic execution prevented under Responsible AI Privacy & Security rules."
                    ),
                    principle=ResponsibleAIPrinciple.PRIVACY_AND_SECURITY,
                    matched_pattern=matched_str,
                )

        return GuardrailResult(
            is_safe=True,
            reason="Input verified safe by prompt injection guard.",
            principle=ResponsibleAIPrinciple.PRIVACY_AND_SECURITY,
        )
