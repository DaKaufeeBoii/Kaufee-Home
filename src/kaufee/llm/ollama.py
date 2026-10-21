"""Ollama local model client adapter with automatic model discovery and fallback."""

from __future__ import annotations

import json
from typing import Any, Optional
import httpx
from kaufee.llm.base import BaseLLMClient


class OllamaClient(BaseLLMClient):
    """Client for local Ollama instances via HTTP API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._auto_select_model_if_needed()

    def get_installed_models(self) -> list[str]:
        """Fetch list of models currently installed in local Ollama."""
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception:
            pass
        return []

    def _auto_select_model_if_needed(self) -> None:
        """If the requested default model is missing, automatically pick from installed models."""
        installed = self.get_installed_models()
        if not installed:
            return

        # Check if the requested model or a variant (e.g. :latest tag) is installed
        for m in installed:
            if m == self.model or m.startswith(f"{self.model}:") or self.model.startswith(f"{m}:"):
                return

        # If user was using the default model and it's not installed, auto-fallback to an installed model
        if self.model == "qwen2.5-coder:7b":
            # Prefer coding or vision-language models, else first available
            fallback = installed[0]
            for m in installed:
                if any(k in m.lower() for k in ["coder", "qwen", "gemma", "llama"]):
                    fallback = m
                    break
            self.model = fallback

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
            raise RuntimeError(f"Ollama generation error ({self.model}): {exc}")

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
            raise RuntimeError(f"Ollama chat error ({self.model}): {exc}")
