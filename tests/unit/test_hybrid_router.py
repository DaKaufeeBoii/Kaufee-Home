"""Unit tests for Two-Tier Hybrid Cascading LLM Router."""

from unittest.mock import MagicMock
import pytest

from kaufee.llm.base import BaseLLMClient
from kaufee.llm.router import HybridRouterClient


class MockLLM(BaseLLMClient):
    def __init__(self, name: str, response: str = "mock output"):
        self.name = name
        self.response = response
        self.call_count = 0

    def generate(self, prompt: str, system_prompt: str | None = None, json_mode: bool = False) -> str:
        self.call_count += 1
        return self.response

    def chat(self, messages: list[dict[str, str]], json_mode: bool = False) -> str:
        self.call_count += 1
        return self.response


def test_hybrid_router_uses_primary_by_default():
    primary = MockLLM("primary", response="local plan")
    fallback = MockLLM("fallback", response="cloud plan")

    router = HybridRouterClient(primary_client=primary, fallback_client=fallback)
    result = router.generate("Create a hello world script")

    assert result == "local plan"
    assert primary.call_count == 1
    assert fallback.call_count == 0
    assert router.last_used_tier == "primary"

    telemetry = router.get_telemetry()
    assert telemetry["total_calls"] == 1
    assert telemetry["escalated_calls"] == 0
    assert telemetry["last_used_tier"] == "primary"


def test_hybrid_router_escalates_on_primary_failure():
    failing_primary = MagicMock(spec=BaseLLMClient)
    failing_primary.generate.side_effect = ConnectionError("Local Ollama service offline")

    fallback = MockLLM("fallback", response="cloud fallback plan")
    router = HybridRouterClient(primary_client=failing_primary, fallback_client=fallback, escalate_on_error=True)

    result = router.generate("Create a script")
    assert result == "cloud fallback plan"
    assert fallback.call_count == 1
    assert router.last_used_tier == "fallback"

    telemetry = router.get_telemetry()
    assert telemetry["total_calls"] == 1
    assert telemetry["escalated_calls"] == 1
    assert telemetry["last_used_tier"] == "fallback"


def test_hybrid_router_escalates_on_repair_directive():
    primary = MockLLM("primary", response="local plan")
    fallback = MockLLM("fallback", response="frontier repaired code")

    router = HybridRouterClient(
        primary_client=primary,
        fallback_client=fallback,
        escalate_on_repair=True,
    )

    # Normal prompt goes to primary
    res1 = router.generate("List the files")
    assert res1 == "local plan"
    assert primary.call_count == 1
    assert fallback.call_count == 0

    # Repair prompt escalates to fallback
    res2 = router.generate("Please perform a code repair and diagnosis on script.py")
    assert res2 == "frontier repaired code"
    assert primary.call_count == 1
    assert fallback.call_count == 1
    assert router.last_used_tier == "fallback"
