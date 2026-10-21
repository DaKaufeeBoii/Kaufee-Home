"""Planner module to convert natural language goals into validated, structured plans."""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from kaufee.llm.base import BaseLLMClient
from kaufee.state.models import Plan, PlanStep, StepStatus, TaskState, ToolCall
from kaufee.tools.registry import ToolRegistry


PLANNER_SYSTEM_PROMPT = """You are Kaufee, a precise, local-first coding and workspace assistant.
Your job is to translate a user's natural language goal into a strictly structured, minimal, sequential execution plan.

CRITICAL RULES:
1. You can ONLY use the registered tools provided below.
2. All file paths MUST be relative to the current workspace root (e.g. 'main.py', 'subfolder/test.py'). Never use absolute paths or '..' path traversal.
3. Every step must have a specific tool, exact arguments matching its schema, and an expected outcome.
4. To create new files or scripts in subfolders (e.g. 'test-001/largest.py'), use 'write_file' with the full relative path. Parent directories are created automatically. NEVER use 'move_file' to create folders.
5. Use 'write_file' to create or write full files. Use 'edit_file' ONLY to modify an existing file.
6. If the goal requires running code and fixing errors, the plan must include writing the code with 'write_file', running it with 'python_runner', and verifying output.
7. Return ONLY a valid JSON object matching this schema:
{
  "plan": [
    {
      "step_number": 1,
      "description": "Short explanation of the step",
      "tool_name": "exact_tool_name",
      "arguments": { "param1": "val1" },
      "expected_outcome": "What success looks like"
    }
  ]
}
No extra text or commentary outside the JSON block.
"""

REPAIR_SYSTEM_PROMPT = """You are Kaufee's diagnostic and repair engine.
A previous step or verification check failed.
Analyze the error and propose a single, targeted corrective tool call (e.g. edit_file or write_file) to repair the issue.

Return ONLY a valid JSON object matching this schema:
{
  "reasoning": "Diagnostic explanation of the failure and proposed fix",
  "tool_name": "exact_tool_name",
  "arguments": { "param1": "val1" }
}
"""


def extract_json_from_text(text: str) -> dict[str, Any]:
    """Robustly extract a JSON object from raw LLM output."""
    cleaned = text.strip()

    # Strip markdown code blocks
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Find first { and last }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str = cleaned[first_brace : last_brace + 1]
        try:
            return json.loads(json_str)
        except Exception:
            pass

    raise ValueError(f"Could not parse valid JSON from response: {text[:200]}...")


class Planner:
    """Creates structured plans and proposes dynamic repair actions."""

    def __init__(self, llm_client: BaseLLMClient, tool_registry: ToolRegistry):
        self.llm = llm_client
        self.registry = tool_registry

    def _normalize_tool_name(self, name: str) -> str:
        """Map common aliases to registered tool names."""
        name_lower = name.lower().strip()
        aliases = {
            "run_python": "python_runner",
            "execute_python": "python_runner",
            "python": "python_runner",
            "run": "python_runner",
            "create_file": "write_file",
            "save_file": "write_file",
            "view_file": "read_file",
            "cat": "read_file",
            "ls": "list_files",
            "dir": "list_files",
            "rm": "delete_file",
            "remove_file": "delete_file",
            "mv": "move_file",
            "rename": "move_file",
        }
        return aliases.get(name_lower, name_lower)

    def create_plan(self, goal: str) -> Plan:
        """Generate a structured plan for the given goal."""
        tools_schema = self.registry.get_schemas()
        prompt = (
            f"GOAL: {goal}\n\n"
            f"AVAILABLE REGISTERED TOOLS:\n{json.dumps(tools_schema, indent=2)}\n\n"
            "Create a structured, step-by-step plan to accomplish this goal."
        )

        raw_response = self.llm.generate(
            prompt=prompt,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            json_mode=True,
        )

        data = extract_json_from_text(raw_response)
        raw_steps = data.get("plan", [])
        if not raw_steps and isinstance(data, list):
            raw_steps = data

        parsed_steps: list[PlanStep] = []
        for idx, s in enumerate(raw_steps, start=1):
            tool_name = self._normalize_tool_name(s.get("tool_name", ""))
            arguments = s.get("arguments", {})
            description = s.get("description", f"Step {idx}")
            expected = s.get("expected_outcome", "")

            # Validate tool is registered
            if not self.registry.get(tool_name):
                raise ValueError(
                    f"Plan step {idx} references unregistered tool '{tool_name}'."
                )

            parsed_steps.append(
                PlanStep(
                    step_number=idx,
                    description=description,
                    tool_name=tool_name,
                    arguments=arguments,
                    expected_outcome=expected,
                    status=StepStatus.PENDING,
                )
            )

        if not parsed_steps:
            raise ValueError(f"No executable steps were generated for goal: {goal}")

        return Plan(goal=goal, steps=parsed_steps)

    def next_action(self, goal: str, state: TaskState) -> Optional[ToolCall]:
        """Determine next tool action, handling normal progression or dynamic repair."""
        # Check if previous step failed and can be repaired
        if state.history:
            last_entry = state.history[-1]
            last_result = last_entry.get("result", {})
            if not last_result.get("success", True) and state.repair_count < state.max_repairs:
                # Propose dynamic repair action
                return self._plan_repair(goal, state, last_entry)

        # Standard plan progression
        if not state.plan or state.current_step_index >= len(state.plan.steps):
            return None

        current_step = state.plan.steps[state.current_step_index]
        return ToolCall(
            tool_name=current_step.tool_name,
            arguments=current_step.arguments,
            reasoning=current_step.description,
        )

    def _plan_repair(self, goal: str, state: TaskState, failure_entry: dict[str, Any]) -> ToolCall:
        """Prompt LLM for a bounded repair action after an error."""
        state.repair_count += 1
        tools_schema = self.registry.get_schemas()
        prompt = (
            f"GOAL: {goal}\n"
            f"REPAIR ATTEMPT: {state.repair_count} of {state.max_repairs}\n\n"
            f"FAILED ACTION: {json.dumps(failure_entry.get('action', {}))}\n"
            f"FAILURE RESULT / ERROR: {json.dumps(failure_entry.get('result', {}))}\n\n"
            f"AVAILABLE TOOLS:\n{json.dumps(tools_schema, indent=2)}\n\n"
            "Propose a single corrective tool call to fix the error."
        )

        try:
            raw_response = self.llm.generate(
                prompt=prompt,
                system_prompt=REPAIR_SYSTEM_PROMPT,
                json_mode=True,
            )
            data = extract_json_from_text(raw_response)
            tool_name = self._normalize_tool_name(data.get("tool_name", "write_file"))
            args = data.get("arguments", {})
            reasoning = data.get("reasoning", f"Repair attempt {state.repair_count}")
            return ToolCall(tool_name=tool_name, arguments=args, reasoning=reasoning)
        except Exception as exc:
            # Fallback if model fails repair response
            return ToolCall(
                tool_name="list_files",
                arguments={"directory": "."},
                reasoning=f"Repair prompt failed ({exc}), checking directory state",
            )
