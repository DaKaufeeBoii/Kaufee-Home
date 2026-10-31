"""Responsible AI Principles and mapping for Agentic AI in Kaufee-Home.

Directly implements the 6 core pillars of Responsible AI:
1. Fairness
2. Reliability & Safety
3. Privacy & Security
4. Inclusiveness
5. Transparency
6. Accountability
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ResponsibleAIPrinciple(str, Enum):
    """The 6 foundational principles of Responsible AI."""

    FAIRNESS = "Fairness"
    RELIABILITY_AND_SAFETY = "Reliability & Safety"
    PRIVACY_AND_SECURITY = "Privacy & Security"
    INCLUSIVENESS = "Inclusiveness"
    TRANSPARENCY = "Transparency"
    ACCOUNTABILITY = "Accountability"


PRINCIPLE_DETAILS: dict[ResponsibleAIPrinciple, dict[str, Any]] = {
    ResponsibleAIPrinciple.FAIRNESS: {
        "title": "Fairness",
        "challenge_or_risk": "Algorithmic bias or asymmetric tool dispatch can produce unfair outcomes.",
        "example": "A coding model prioritizes certain libraries or fails to give equal evaluation across user environments.",
        "agentic_mitigation": (
            "Deterministic, unbiased policy rules and standard AST/exit-code verifiers that evaluate "
            "all code and tasks strictly against objective postconditions without model-favoring bias."
        ),
        "enforcing_components": ["PolicyEngine", "ObjectiveVerifier", "ToolRegistry"],
    },
    ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY: {
        "title": "Reliability & Safety",
        "challenge_or_risk": "Autonomous execution errors, infinite loops, or corrupted code may cause harm.",
        "example": "An autonomous agent gets stuck in a loop overwriting files or runs unverified broken code.",
        "agentic_mitigation": (
            "Independent AST syntax verification, circuit breakers for repetitive tool loops, bounded repair budgets, "
            "atomic file operations, and pre-action backup snapshots for instant rollback."
        ),
        "enforcing_components": [
            "CircuitBreaker",
            "ObjectiveVerifier",
            "BoundedPythonRunner",
            "WorkspaceManager",
        ],
    },
    ResponsibleAIPrinciple.PRIVACY_AND_SECURITY: {
        "title": "Privacy & Security",
        "challenge_or_risk": "Private user credentials, tokens, or system files could be exposed or compromised.",
        "example": "An agent exfiltrates API keys, accesses .env/id_rsa, or falls victim to indirect prompt injection.",
        "agentic_mitigation": (
            "Strict workspace confinement (blocking path traversal, symlink escapes, and protected files like .env/.ssh), "
            "automatic sensitive data redaction in logs/output, and indirect prompt injection guards."
        ),
        "enforcing_components": [
            "WorkspacePathSanitizer",
            "SensitiveDataRedactor",
            "PromptInjectionGuard",
            "PolicyEngine",
        ],
    },
    ResponsibleAIPrinciple.INCLUSIVENESS: {
        "title": "Inclusiveness",
        "challenge_or_risk": "Complex agent interfaces and cryptic stack traces may alienate non-technical or impaired users.",
        "example": "A CLI tool only outputs raw JSON and color-dependent symbols without clear, human-accessible summaries.",
        "agentic_mitigation": (
            "Plain-English task status reporting, multi-level verbosity, accessible text summaries, "
            "clear diagnostic messages explaining reasons for blocks and failures, and device portability."
        ),
        "enforcing_components": ["CLI", "StepReporter", "ErrorDiagnostics"],
    },
    ResponsibleAIPrinciple.TRANSPARENCY: {
        "title": "Transparency",
        "challenge_or_risk": "Users must understand and trust why an autonomous agent took specific actions.",
        "example": "An AI agent modifies project files without explaining the plan, tool choice, or reasoning.",
        "agentic_mitigation": (
            "Explicit two-phase planning showing every step before execution, real-time thought and action streaming, "
            "and immutable structured JSON audit logging mapping every action to its policy decision and rationale."
        ),
        "enforcing_components": ["Planner", "AuditLogger", "StepReporter"],
    },
    ResponsibleAIPrinciple.ACCOUNTABILITY: {
        "title": "Accountability",
        "challenge_or_risk": "Who is liable for automated decisions and destructive actions taken by the AI agent?",
        "example": "An autonomous agent deletes critical files or installs unauthorized software without human approval.",
        "agentic_mitigation": (
            "Human-in-the-loop (HITL) approval gates for destructive and executing operations, configurable autonomy modes "
            "(manual, assisted, autonomous), and durable, auditable logs recording who approved each action."
        ),
        "enforcing_components": [
            "ApprovalGate",
            "AutonomyPolicy",
            "AuditLogger",
            "PolicyEngine",
        ],
    },
}


def get_principle_info(principle: ResponsibleAIPrinciple) -> dict[str, Any]:
    """Retrieve detailed description and mitigations for a Responsible AI principle."""
    return PRINCIPLE_DETAILS[principle]
