"""Deterministic Mock LLM client for offline execution and testing."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional
from kaufee.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """
    Mock client providing deterministic plan responses for benchmarks and testing.
    Does not require a live network connection or local Ollama server.
    """

    def __init__(self, custom_handler: Optional[Callable[[str], str]] = None):
        self.custom_handler = custom_handler
        self.call_history: list[dict[str, Any]] = []

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        self.call_history.append({"prompt": prompt, "system": system_prompt})

        if self.custom_handler:
            return self.custom_handler(prompt)

        # Extract only the goal line to avoid matching tool schema descriptions
        goal_text = prompt
        for line in prompt.splitlines():
            if line.startswith("GOAL:"):
                goal_text = line.replace("GOAL:", "").strip()
                break

        lower_goal = goal_text.lower()
        lower_prompt = prompt.lower()

        # Check for repair / retry prompt
        if "repair attempt" in lower_prompt or "failure result" in lower_prompt:
            if "syntax" in lower_prompt or "broken.py" in lower_prompt:
                return json.dumps({
                    "reasoning": "Fix the syntax error in broken.py by providing correct Python syntax.",
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "broken.py",
                        "content": "def greet(name):\n    return f'Hello, {name}!'\n\nif __name__ == '__main__':\n    print(greet('World'))\n",
                    },
                })
            elif "zerodivision" in lower_prompt or "calc.py" in lower_prompt:
                return json.dumps({
                    "reasoning": "Fix the ZeroDivisionError in calc.py with safe division.",
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "calc.py",
                        "content": "def safe_divide(a, b):\n    if b == 0:\n        return 0\n    return a / b\n\nif __name__ == '__main__':\n    print(safe_divide(10, 2))\n",
                    },
                })
            else:
                return json.dumps({
                    "reasoning": "Repair step: list files to re-evaluate.",
                    "tool_name": "list_files",
                    "arguments": {"directory": "."},
                })

        # Scenario: Draw triangle in Python
        if "triangle" in lower_goal:
            return json.dumps({
                "plan": [
                    {
                        "step_number": 1,
                        "description": "Create triangle.py that outputs an ASCII triangle",
                        "tool_name": "write_file",
                        "arguments": {
                            "path": "triangle.py",
                            "content": (
                                "def draw_triangle(height=5):\n"
                                "    for i in range(1, height + 1):\n"
                                "        print(' ' * (height - i) + '*' * (2 * i - 1))\n\n"
                                "if __name__ == '__main__':\n"
                                "    draw_triangle()\n"
                            ),
                        },
                        "expected_outcome": "triangle.py created with ASCII triangle drawing code",
                    },
                    {
                        "step_number": 2,
                        "description": "Execute triangle.py and inspect output",
                        "tool_name": "python_runner",
                        "arguments": {
                            "script_path": "triangle.py",
                        },
                        "expected_outcome": "Program runs successfully with exit code 0",
                    },
                ]
            })

        # Scenario: Organize files / move files
        if "organize" in lower_goal or "move" in lower_goal or "texts" in lower_goal:
            return json.dumps({
                "plan": [
                    {
                        "step_number": 1,
                        "description": "List files in workspace",
                        "tool_name": "list_files",
                        "arguments": {"directory": "."},
                        "expected_outcome": "List of current workspace files",
                    },
                    {
                        "step_number": 2,
                        "description": "Move sample.txt to texts directory",
                        "tool_name": "move_file",
                        "arguments": {
                            "source_path": "sample.txt",
                            "destination_path": "texts/sample.txt",
                        },
                        "expected_outcome": "sample.txt moved into texts folder",
                    },
                ]
            })

        # Scenario: Fix syntax error
        if "syntax" in lower_goal or "broken" in lower_goal:
            return json.dumps({
                "plan": [
                    {
                        "step_number": 1,
                        "description": "Read broken.py to diagnose syntax error",
                        "tool_name": "read_file",
                        "arguments": {"path": "broken.py"},
                        "expected_outcome": "Inspect broken code",
                    },
                    {
                        "step_number": 2,
                        "description": "Write corrected Python code into broken.py",
                        "tool_name": "write_file",
                        "arguments": {
                            "path": "broken.py",
                            "content": "print('Fixed syntax error')\n",
                        },
                        "expected_outcome": "Syntax error resolved",
                    },
                    {
                        "step_number": 3,
                        "description": "Run broken.py to verify fix",
                        "tool_name": "python_runner",
                        "arguments": {"script_path": "broken.py"},
                        "expected_outcome": "Runs successfully with exit code 0",
                    },
                ]
            })

        # Scenario: Add function / Project modification
        if "add function" in lower_goal or "modify" in lower_goal:
            return json.dumps({
                "plan": [
                    {
                        "step_number": 1,
                        "description": "Read existing math_utils.py",
                        "tool_name": "read_file",
                        "arguments": {"path": "math_utils.py"},
                        "expected_outcome": "View existing functions",
                    },
                    {
                        "step_number": 2,
                        "description": "Append multiply function",
                        "tool_name": "write_file",
                        "arguments": {
                            "path": "math_utils.py",
                            "content": "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
                        },
                        "expected_outcome": "multiply function added",
                    },
                ]
            })

        # Generic default plan
        return json.dumps({
            "plan": [
                {
                    "step_number": 1,
                    "description": "Inspect workspace files",
                    "tool_name": "list_files",
                    "arguments": {"directory": "."},
                    "expected_outcome": "Workspace contents listed",
                }
            ]
        })

    def chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        last_msg = messages[-1]["content"] if messages else ""
        return self.generate(last_msg, json_mode=json_mode)
