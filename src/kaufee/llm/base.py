"""Base interface for LLM client adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseLLMClient(ABC):
    """Abstract interface for LLM communication."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        """Generate text completion from a prompt."""
        pass

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        """Perform a multi-turn chat interaction."""
        pass
