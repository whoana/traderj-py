"""Tests for CircuitBreaker."""

from time import monotonic

from engine.execution.circuit_breaker import CBState, CircuitBreaker


class TestCircuitBreakerInit:
    def test_initial_state(self):
        cb = CircuitBreaker()
        assert cb.state == CBState.CLOSED
        assert cb.consecutive_failures == 0
        assert cb.allow_request() is True

    def test_custom_threshold(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_seconds=60.0)
        assert cb.failure_threshold == 5
        assert cb.recovery_seconds == 60.0


class TestCircuitBreakerTransitions:
    def test_success_keeps_closed(self):
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == CBState.CLOSED
        assert cb.consecutive_failures == 0

    def test_failure_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CBState.CLOSED
        assert cb.consecutive_failures == 2
        assert cb.allow_request() is True

    def test_failure_trips_to_open(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CBState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == CBState.CLOSED

    def test_open_to_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
        cb.record_failure()
        assert cb._state == CBState.OPEN
        # Simulate time passage
        cb._opened_at = monotonic() - 1.0
        assert cb.state == CBState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
        cb.record_failure()
        cb._opened_at = monotonic() - 1.0
        _ = cb.state  # trigger transition to HALF_OPEN
        cb.record_success()
        assert cb.state == CBState.CLOSED
        assert cb.consecutive_failures == 0

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.01)
        cb.record_failure()
        cb._opened_at = monotonic() - 1.0
        _ = cb.state  # HALF_OPEN
        cb.record_failure()
        assert cb._state == CBState.OPEN
        assert cb.allow_request() is False

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CBState.OPEN
        cb.reset()
        assert cb.state == CBState.CLOSED
        assert cb.consecutive_failures == 0

    def test_open_blocks_all_requests(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.allow_request() is False
        assert cb.allow_request() is False  # stays blocked
