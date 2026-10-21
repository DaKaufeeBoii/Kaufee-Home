"""Ollama local model client adapter."""

from __future__ import annotations

import json
from typing import Any, Optional
import httpx
from kaufee.llm.base import BaseLLMClient


class OllamaClient(BaseLLMClient):
    """Client for local Ollama instances via HTTP API."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5-coder:7b", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        url = f"{self.base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")
        except httpx.ConnectError:
            raise ConnectionError(
                f"Could not connect to Ollama at {self.base_url}. "
                "Ensure Ollama is running (`ollama serve`), or run with `--provider mock` or configure remote API."
            )
        except Exception as exc:
            raise RuntimeError(f"Ollama generation error: {exc}")

    def chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                msg = data.get("message", {})
                return msg.get("content", "")
        except httpx.ConnectError:
            raise ConnectionError(
                f"Could not connect to Ollama at {self.base_url}. "
                "Ensure Ollama is running (`ollama serve`), or switch provider with `--provider mock`."
            )
        except Exception as exc:
            raise RuntimeError(f"Ollama chat error: {exc}")
