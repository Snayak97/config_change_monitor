"""
Unit tests for the Circuit Breaker pattern.
"""

import time
from src.notifier.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=3, recovery_timeout_seconds=0.2)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_transitions_to_open_on_threshold_failures(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=3, recovery_timeout_seconds=0.2)
        err = RuntimeError("network drop")

        cb.record_failure(err)
        assert cb.state == CircuitState.CLOSED
        cb.record_failure(err)
        assert cb.state == CircuitState.CLOSED

        # 3rd failure reaches threshold
        cb.record_failure(err)
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_recovery_timeout_transitions_to_half_open_and_resets_on_success(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout_seconds=0.1)
        err = RuntimeError("timeout")

        cb.record_failure(err)
        cb.record_failure(err)
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

        # Wait for recovery timeout
        time.sleep(0.15)
        # can_execute triggers probe transition to HALF_OPEN
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

        # Probe succeeds -> CLOSED
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout_seconds=0.1)
        err = RuntimeError("timeout")

        cb.record_failure(err)
        cb.record_failure(err)
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

        # Probe fails -> OPEN
        cb.record_failure(err)
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False
