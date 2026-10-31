"""Agent execution loop implementing verifiable tool use and bounded recovery."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, Optional
from kaufee.agent.planner import Planner
from kaufee.agent.verifier import Verifier
from kaufee.safety.circuit_breaker import AgentCircuitBreaker
from kaufee.safety.guardrails import PromptInjectionGuard
from kaufee.safety.principles import ResponsibleAIPrinciple
from kaufee.safety.policy import PolicyEngine
from kaufee.safety.redactor import redact_data
from kaufee.state.audit import AuditLogger
from kaufee.state.models import (
    PlanStep,
    PolicyDecision,
    StepStatus,
    TaskState,
    TaskStatus,
    ToolCall,
    ToolResult,
)
from kaufee.tools.registry import ToolRegistry


ApprovalCallback = Callable[[ToolCall, PolicyDecision], bool]
StepCallback = Callable[[str, TaskState, Optional[ToolCall], Optional[ToolResult]], None]


class AgentLoop:
    """Executes the core agent loop with strict policy checks, logging, and verification."""

    def __init__(
        self,
        planner: Planner,
        tool_registry: ToolRegistry,
        policy_engine: PolicyEngine,
        verifier: Verifier,
        audit_logger: AuditLogger,
        workspace_root: Path,
        approval_callback: Optional[ApprovalCallback] = None,
        step_callback: Optional[StepCallback] = None,
    ):
        self.planner = planner
        self.tools = tool_registry
        self.policy = policy_engine
        self.verifier = verifier
        self.audit = audit_logger
        self.workspace_root = workspace_root.resolve()
        self.approval_callback = approval_callback
        self.step_callback = step_callback
        self.cancellation_event = threading.Event()
        self.cancellation_event.clear()

        # Responsible AI safety guardians
        cfg = getattr(self.policy, "config", None)
        inj_enabled = getattr(cfg, "enable_prompt_injection_guard", True) if cfg else True
        cb_threshold = getattr(cfg, "circuit_breaker_threshold", 3) if cfg else 3

        self.injection_guard = PromptInjectionGuard(enabled=inj_enabled)
        self.circuit_breaker = AgentCircuitBreaker(repetition_threshold=cb_threshold)

    def cancel(self) -> None:
        """Signal active work, including a running Python child, to stop."""
        self.cancellation_event.set()

    def run(self, state: TaskState) -> TaskState:
        """Run execution loop until completion, failure, cancellation, or step exhaustion."""
        state.status = TaskStatus.RUNNING
        self.audit.log(
            "TASK_START",
            {"task_id": state.task_id, "goal": state.goal},
            principle=ResponsibleAIPrinciple.ACCOUNTABILITY.value,
        )
        self._notify("TASK_START", state)

        # 0. Prompt Injection & Malicious Input Guardrail Check (Privacy & Security)
        guard_res = self.injection_guard.check_input(state.goal)
        if not guard_res.is_safe:
            self.audit.log(
                "GUARDRAIL_BLOCKED",
                {"reason": guard_res.reason, "pattern": guard_res.matched_pattern},
                principle=guard_res.principle.value,
            )
            self._notify("GUARDRAIL_BLOCKED", state)
            return state.fail(guard_res.reason)

        # 1. Initial planning step (Transparency)
        try:
            plan = self.planner.create_plan(state.goal)
            state.plan = plan
            self.audit.log(
                "PLAN_CREATED",
                {"plan": plan.model_dump()},
                principle=ResponsibleAIPrinciple.TRANSPARENCY.value,
            )
            self._notify("PLAN_CREATED", state)
        except Exception as exc:
            err_msg = f"Planning failed: {exc}"
            self.audit.log(
                "PLAN_FAILED",
                {"error": err_msg},
                principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY.value,
            )
            return state.fail(err_msg)

        blocked_actions_signatures: set[str] = set()

        # 2. Main iterative step loop
        for step_idx in range(state.max_steps):
            if state.is_cancelled() or self.cancellation_event.is_set():
                self.audit.log(
                    "TASK_CANCELLED",
                    {"step": step_idx},
                    principle=ResponsibleAIPrinciple.ACCOUNTABILITY.value,
                )
                return state.cancel()

            # Check if plan steps are complete
            if state.plan_is_complete():
                v_result = self.verifier.verify(state.goal, state)
                self.audit.log(
                    "VERIFICATION_RUN",
                    {"result": v_result.model_dump()},
                    principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY.value,
                )

                if v_result.success:
                    self.audit.log(
                        "TASK_COMPLETED",
                        {"checks_passed": len(v_result.checks)},
                        principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY.value,
                    )
                    self._notify("TASK_COMPLETED", state)
                    return state.complete(v_result)

                # Verification failed
                state.verification_result = v_result
                if state.repair_count >= state.max_repairs:
                    err = f"Verification failed after {state.repair_count} repairs: {v_result.message}"
                    self.audit.log(
                        "TASK_FAILED",
                        {"reason": err},
                        principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY.value,
                    )
                    self._notify("TASK_FAILED", state)
                    return state.fail(err)

                # Formulate failure details and log
                failed_checks = [c for c in v_result.checks if not c.passed]
                fail_detail = "; ".join(f"{c.name}: {c.details}" for c in failed_checks)
                self.audit.log(
                    "VERIFICATION_FAILED",
                    {"details": fail_detail},
                    principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY.value,
                )
                failure_entry = {
                    "action": {"tool_name": "verify", "arguments": {"goal": state.goal}},
                    "result": {"success": False, "output": "", "error": f"Verification failed — {fail_detail}"},
                    "status": "FAILED",
                }
                state.history.append(redact_data(failure_entry))
                self._notify("TASK_FAILED", state)

                # Propose corrective repair action from planner
                action = self.planner._plan_repair(state.goal, state, failure_entry)

                # Append repair action as a new step in the plan so the execution pointer advances
                repair_step = PlanStep(
                    step_number=len(state.plan.steps) + 1 if state.plan else 1,
                    description=action.reasoning or f"Repair attempt {state.repair_count}",
                    tool_name=action.tool_name,
                    arguments=action.arguments,
                    expected_outcome=f"Repair failure: {fail_detail}",
                    status=StepStatus.PENDING,
                )
                if state.plan:
                    state.plan.steps.append(repair_step)
            else:
                # Determine next action
                action = self.planner.next_action(state.goal, state)
                if action is None:
                    # No next action proposed, re-verify final outcome
                    v_result = self.verifier.verify(state.goal, state)
                    if v_result.success:
                        return state.complete(v_result)
                    return state.fail("No valid next action proposed and verification failed.")

            # Safety Circuit Breaker: Evaluate for infinite repetition loop before execution
            cb_eval = self.circuit_breaker.record_and_evaluate_action(action)
            if cb_eval.is_tripped:
                self.audit.log(
                    "CIRCUIT_BREAKER_TRIPPED",
                    {"reason": cb_eval.reason},
                    principle=cb_eval.principle.value,
                )
                self._notify("ACTION_BLOCKED", state, action=action)
                return state.fail(cb_eval.reason)

            action_sig = f"{action.tool_name}:{sorted(action.arguments.items())}"
            if action_sig in blocked_actions_signatures:
                return state.fail(f"Loop detected on previously blocked action '{action.tool_name}'.")

            # Validate action with Policy Engine
            decision = self.policy.validate(action, self.workspace_root)
            self.audit.log(
                "POLICY_DECISION",
                {
                    "action": action.model_dump(),
                    "decision": decision.model_dump(),
                },
                principle=decision.principle,
            )

            if not decision.allowed:
                blocked_actions_signatures.add(action_sig)
                self.audit.log(
                    "ACTION_BLOCKED",
                    {"reason": decision.reason},
                    principle=decision.principle,
                )
                state.history.append(redact_data({
                    "action": action.model_dump(),
                    "decision": decision.model_dump(),
                    "result": {
                        "success": False,
                        "output": "",
                        "error": decision.reason,
                    },
                    "status": "BLOCKED",
                }))
                self._notify("ACTION_BLOCKED", state, action=action)
                # If a critical block occurs, stop or attempt repair
                if decision.risk_level.value == "CRITICAL":
                    return state.fail(f"Safety violation blocked: {decision.reason}")
                continue

            # Check approval requirements (Accountability)
            if decision.requires_approval:
                self.audit.log(
                    "APPROVAL_PROMPT",
                    {"action": action.model_dump()},
                    principle=ResponsibleAIPrinciple.ACCOUNTABILITY.value,
                )
                approved = False
                if self.approval_callback:
                    approved = self.approval_callback(action, decision)

                if not approved:
                    blocked_actions_signatures.add(action_sig)
                    self.audit.log(
                        "APPROVAL_DENIED",
                        {"action": action.model_dump()},
                        principle=ResponsibleAIPrinciple.ACCOUNTABILITY.value,
                    )
                    state.history.append(redact_data({
                        "action": action.model_dump(),
                        "decision": decision.model_dump(),
                        "status": "DENIED",
                    }))
                    self._notify("APPROVAL_DENIED", state, action=action)
                    return state.fail(f"Action '{action.tool_name}' denied by user approval.")

            # Execute tool
            state.tool_calls_attempted += 1
            self._notify("TOOL_EXEC_START", state, action=action)
            tool_result = self.tools.execute(
                action, self.workspace_root, cancellation_event=self.cancellation_event
            )

            # Record outcome in circuit breaker
            cb_result = self.circuit_breaker.record_result(tool_result)
            if cb_result.is_tripped:
                self.audit.log(
                    "CIRCUIT_BREAKER_TRIPPED",
                    {"reason": cb_result.reason},
                    principle=cb_result.principle.value,
                )
                return state.fail(cb_result.reason)

            if state.is_cancelled() or self.cancellation_event.is_set():
                self.audit.log(
                    "TASK_CANCELLED",
                    {"step": step_idx, "during_tool": action.tool_name},
                    principle=ResponsibleAIPrinciple.ACCOUNTABILITY.value,
                )
                return state.cancel()

            self.audit.log(
                "TOOL_EXEC",
                {
                    "action": action.model_dump(),
                    "result": tool_result.model_dump(),
                },
                principle=decision.principle or ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY.value,
            )

            if tool_result.success:
                state.tool_calls_succeeded += 1
                state.history.append(redact_data({
                    "action": action.model_dump(),
                    "result": tool_result.model_dump(),
                    "status": "SUCCESS",
                }))
                # If executing planned step, advance step pointer
                if state.plan and state.current_step_index < len(state.plan.steps):
                    step = state.plan.steps[state.current_step_index]
                    if step.tool_name == action.tool_name:
                        step.status = StepStatus.SUCCESS
                        step.result = tool_result
                        state.current_step_index += 1
                self._notify("TOOL_EXEC_SUCCESS", state, action=action, result=tool_result)
            else:
                state.tool_calls_failed += 1
                state.history.append(redact_data({
                    "action": action.model_dump(),
                    "result": tool_result.model_dump(),
                    "status": "FAILED",
                }))
                self._notify("TOOL_EXEC_FAILED", state, action=action, result=tool_result)

                if state.repair_count >= state.max_repairs:
                    err = f"Tool '{action.tool_name}' failed and repair limit ({state.max_repairs}) reached: {tool_result.error}"
                    return state.fail(err)

        # Max steps budget exceeded
        v_result = self.verifier.verify(state.goal, state)
        if v_result.success:
            return state.complete(v_result)
        return state.fail(f"Execution budget exceeded ({state.max_steps} steps) without verifying task success.")

    def _notify(
        self,
        event: str,
        state: TaskState,
        action: Optional[ToolCall] = None,
        result: Optional[ToolResult] = None,
    ) -> None:
        if self.step_callback:
            try:
                self.step_callback(event, state, action, result)
            except Exception:
                pass
