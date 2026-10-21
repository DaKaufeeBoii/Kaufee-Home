"""Agent controller orchestrating component lifecycle, limits, and task execution."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
from kaufee.agent.loop import AgentLoop, ApprovalCallback, StepCallback
from kaufee.agent.planner import Planner
from kaufee.agent.verifier import Verifier
from kaufee.config import KaufeeConfig
from kaufee.llm.api import RemoteAPIClient
from kaufee.llm.base import BaseLLMClient
from kaufee.llm.mock import MockLLMClient
from kaufee.llm.ollama import OllamaClient
from kaufee.safety.policy import PolicyEngine
from kaufee.state.audit import AuditLogger
from kaufee.state.models import TaskState, TaskStatus, ToolCall
from kaufee.state.store import StateStore
from kaufee.tools.registry import ToolRegistry


class AgentController:
    """High-level controller coordinating agent execution, state, and safety."""

    def __init__(
        self,
        config: Optional[KaufeeConfig] = None,
        llm_client: Optional[BaseLLMClient] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.config = config or KaufeeConfig.load()
        self.workspace_root = self.config.workspace_root
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        # Persistence & Store
        state_dir = self.workspace_root / ".kaufee" / "state"
        self.store = StateStore(state_dir)

        # Tools & Policy
        self.tools = tool_registry or ToolRegistry.create_default(self.config)
        self.policy = PolicyEngine(self.config)

        # LLM Client
        self.llm = llm_client or self._resolve_llm_client()

        # Planner & Verifier
        self.planner = Planner(self.llm, self.tools)
        self.verifier = Verifier(self.workspace_root)

        self._current_state: Optional[TaskState] = None

    def _resolve_llm_client(self) -> BaseLLMClient:
        provider = self.config.llm_provider.lower().strip()
        if provider == "mock":
            return MockLLMClient()
        elif provider == "remote":
            return RemoteAPIClient(
                base_url=self.config.remote_api_base_url,
                api_key=self.config.remote_api_key,
                model=self.config.remote_model,
            )
        else:
            client = OllamaClient(
                base_url=self.config.ollama_base_url,
                model=self.config.ollama_model,
            )
            self.config.ollama_model = client.model
            return client

    def run_task(
        self,
        goal: str,
        approval_callback: Optional[ApprovalCallback] = None,
        step_callback: Optional[StepCallback] = None,
    ) -> TaskState:
        """Create and execute a task for the given goal."""
        state = TaskState(
            goal=goal,
            workspace_root=str(self.workspace_root),
            max_steps=self.config.max_steps,
            max_repairs=self.config.max_repairs,
        )
        self._current_state = state

        audit_logger = AuditLogger(self.config.audit_dir, state.task_id)

        loop = AgentLoop(
            planner=self.planner,
            tool_registry=self.tools,
            policy_engine=self.policy,
            verifier=self.verifier,
            audit_logger=audit_logger,
            workspace_root=self.workspace_root,
            approval_callback=approval_callback,
            step_callback=step_callback,
        )

        try:
            final_state = loop.run(state)
        except Exception as exc:
            final_state = state.fail(f"Unhandled exception during task loop: {exc}")

        # Persist final state
        try:
            self.store.save(final_state)
        except Exception:
            pass

        return final_state

    def cancel_current_task(self, reason: str = "Interrupted by user") -> Optional[TaskState]:
        """Cancel active task execution."""
        if self._current_state and self._current_state.status == TaskStatus.RUNNING:
            return self._current_state.cancel(reason)
        return None
