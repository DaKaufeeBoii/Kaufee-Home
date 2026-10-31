"""Circuit breaker to prevent runaway loops and cascading failures."""

from __future__ import annotations

from typing import NamedTuple, Optional
from kaufee.safety.principles import ResponsibleAIPrinciple
from kaufee.state.models import ToolCall, ToolResult


class CircuitBreakerStatus(NamedTuple):
    is_tripped: bool
    reason: str
    principle: ResponsibleAIPrinciple


class AgentCircuitBreaker:
    """Monitors tool calls and execution outcomes to intercept infinite loops and cascading errors."""

    def __init__(self, repetition_threshold: int = 3, consecutive_failure_threshold: int = 4):
        self.repetition_threshold = repetition_threshold
        self.consecutive_failure_threshold = consecutive_failure_threshold
        self._action_history: list[str] = []
        self._consecutive_failures: int = 0
        self._is_tripped: bool = False
        self._trip_reason: Optional[str] = None

    def record_and_evaluate_action(self, action: ToolCall) -> CircuitBreakerStatus:
        """Evaluate if proposed action constitutes an infinite repetition loop before execution."""
        if self._is_tripped:
            return CircuitBreakerStatus(
                is_tripped=True,
                reason=self._trip_reason or "Circuit breaker already tripped.",
                principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY,
            )

        # Generate deterministic signature of action and arguments
        sig = f"{action.tool_name}:{sorted(str(v) for v in action.arguments.items())}"
        self._action_history.append(sig)

        # Check if the last N actions are identical
        if len(self._action_history) >= self.repetition_threshold:
            recent = self._action_history[-self.repetition_threshold :]
            if all(s == sig for s in recent):
                self._is_tripped = True
                self._trip_reason = (
                    f"Circuit Breaker Tripped: Action '{action.tool_name}' was repeated "
                    f"{self.repetition_threshold} times identically without state progression. "
                    "Halting to prevent an infinite loop (Responsible AI: Reliability & Safety)."
                )
                return CircuitBreakerStatus(
                    is_tripped=True,
                    reason=self._trip_reason,
                    principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY,
                )

        return CircuitBreakerStatus(
            is_tripped=False,
            reason="Action within normal execution boundaries.",
            principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY,
        )

    def record_result(self, result: ToolResult) -> CircuitBreakerStatus:
        """Update circuit breaker metrics with tool outcome."""
        if not result.success:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.consecutive_failure_threshold:
                self._is_tripped = True
                self._trip_reason = (
                    f"Circuit Breaker Tripped: {self._consecutive_failures} consecutive tool failures occurred. "
                    "Halting execution to prevent cascading errors (Responsible AI: Reliability & Safety)."
                )
                return CircuitBreakerStatus(
                    is_tripped=True,
                    reason=self._trip_reason,
                    principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY,
                )
        else:
            self._consecutive_failures = 0

        return CircuitBreakerStatus(
            is_tripped=self._is_tripped,
            reason=self._trip_reason or "Execution state healthy.",
            principle=ResponsibleAIPrinciple.RELIABILITY_AND_SAFETY,
        )

    def reset(self) -> None:
        """Reset circuit breaker state."""
        self._action_history.clear()
        self._consecutive_failures = 0
        self._is_tripped = False
        self._trip_reason = None
