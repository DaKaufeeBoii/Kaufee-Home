"""Unit tests for safety circuit breaker preventing runaway loops."""

from kaufee.safety.circuit_breaker import AgentCircuitBreaker
from kaufee.state.models import ToolCall, ToolResult


def test_circuit_breaker_trips_on_repetitive_identical_calls():
    cb = AgentCircuitBreaker(repetition_threshold=3)
    call = ToolCall(tool_name="write_file", arguments={"path": "main.py", "content": "print('loop')"})

    # Call 1
    s1 = cb.record_and_evaluate_action(call)
    assert not s1.is_tripped

    # Call 2
    s2 = cb.record_and_evaluate_action(call)
    assert not s2.is_tripped

    # Call 3 (identical) -> should trip
    s3 = cb.record_and_evaluate_action(call)
    assert s3.is_tripped
    assert "Circuit Breaker Tripped" in s3.reason
    assert "repeated 3 times" in s3.reason


def test_circuit_breaker_trips_on_consecutive_failures():
    cb = AgentCircuitBreaker(consecutive_failure_threshold=3)
    res_fail = ToolResult(call_id="1", tool_name="run_python", success=False, error="Syntax error")
    res_success = ToolResult(call_id="2", tool_name="run_python", success=True, output="OK")

    assert not cb.record_result(res_fail).is_tripped
    assert not cb.record_result(res_fail).is_tripped
    # Third failure -> trip
    tripped = cb.record_result(res_fail)
    assert tripped.is_tripped
    assert "consecutive tool failures" in tripped.reason

    # Reset
    cb.reset()
    assert not cb.record_result(res_fail).is_tripped
    assert not cb.record_result(res_success).is_tripped
