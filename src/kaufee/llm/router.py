"""Two-tier hybrid cascading router adapter for local-first execution with cloud escalation."""

from __future__ import annotations

import logging
from typing import Any, Optional

from kaufee.llm.base import BaseLLMClient

logger = logging.getLogger("kaufee.llm.router")


class HybridRouterClient(BaseLLMClient):
    """
    Two-Tier Hybrid LLM Client Router.
    Tier 1 (Primary): Runs locally (e.g. Ollama or Mock) with $0 marginal cost.
    Tier 2 (Fallback/Escalation): Automatically escalates complex repairs or recovers
    from local timeouts/exceptions using a frontier remote model (OpenAI, Claude, etc.).
    """

    def __init__(
        self,
        primary_client: BaseLLMClient,
        fallback_client: Optional[BaseLLMClient] = None,
        escalate_on_error: bool = True,
        escalate_on_repair: bool = False,
    ):
        self.primary_client = primary_client
        self.fallback_client = fallback_client
        self.escalate_on_error = escalate_on_error
        self.escalate_on_repair = escalate_on_repair

        self.last_used_tier: str = "primary"
        self.total_calls: int = 0
        self.escalated_calls: int = 0

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        self.total_calls += 1

        # Check if this is a repair prompt and escalate_on_repair is enabled
        is_repair = "repair" in prompt.lower() or "diagnosis" in prompt.lower()
        if is_repair and self.escalate_on_repair and self.fallback_client is not None:
            self.last_used_tier = "fallback"
            self.escalated_calls += 1
            return self.fallback_client.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)

        try:
            res = self.primary_client.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)
            if res and res.strip():
                self.last_used_tier = "primary"
                return res
            # If primary produced empty output and fallback is available, escalate
            if self.fallback_client is not None and self.escalate_on_error:
                self.last_used_tier = "fallback"
                self.escalated_calls += 1
                return self.fallback_client.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)
            return res
        except Exception as exc:
            if self.fallback_client is not None and self.escalate_on_error:
                self.last_used_tier = "fallback"
                self.escalated_calls += 1
                logger.warning("Primary LLM client error (%s); cascading to fallback tier: %s", type(exc).__name__, exc)
                return self.fallback_client.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)
            raise

    def chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        self.total_calls += 1

        # Check repair content in messages
        is_repair = any("repair" in m.get("content", "").lower() for m in messages)
        if is_repair and self.escalate_on_repair and self.fallback_client is not None:
            self.last_used_tier = "fallback"
            self.escalated_calls += 1
            return self.fallback_client.chat(messages, json_mode=json_mode)

        try:
            res = self.primary_client.chat(messages, json_mode=json_mode)
            if res and res.strip():
                self.last_used_tier = "primary"
                return res
            if self.fallback_client is not None and self.escalate_on_error:
                self.last_used_tier = "fallback"
                self.escalated_calls += 1
                return self.fallback_client.chat(messages, json_mode=json_mode)
            return res
        except Exception as exc:
            if self.fallback_client is not None and self.escalate_on_error:
                self.last_used_tier = "fallback"
                self.escalated_calls += 1
                logger.warning("Primary LLM client error (%s); cascading to fallback tier: %s", type(exc).__name__, exc)
                return self.fallback_client.chat(messages, json_mode=json_mode)
            raise

    def get_telemetry(self) -> dict[str, Any]:
        """Return routing metrics for audit logging."""
        return {
            "total_calls": self.total_calls,
            "escalated_calls": self.escalated_calls,
            "last_used_tier": self.last_used_tier,
            "has_fallback": self.fallback_client is not None,
        }
