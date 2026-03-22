"""Circuit Breaker for order execution.

States: CLOSED (normal) → OPEN (blocked) → HALF_OPEN (trial).
- 3 consecutive failures → OPEN
- After recovery_seconds (300s) → HALF_OPEN
- HALF_OPEN: 1 attempt allowed; success → CLOSED, failure → OPEN
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic

logger = logging.getLogger(__name__)


class CBState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_seconds: float = 300.0  # 5 minutes

    _state: CBState = field(default=CBState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)

    @property
    def state(self) -> CBState:
        if self._state == CBState.OPEN:
            elapsed = monotonic() - self._opened_at
            if elapsed >= self.recovery_seconds:
                self._state = CBState.HALF_OPEN
                logger.info(
                    "CircuitBreaker OPEN → HALF_OPEN after %.1fs", elapsed
                )
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def allow_request(self) -> bool:
        s = self.state
        return s in (CBState.CLOSED, CBState.HALF_OPEN)

    def record_success(self) -> None:
        prev = self._state
        self._state = CBState.CLOSED
        self._consecutive_failures = 0
        if prev != CBState.CLOSED:
            logger.info("CircuitBreaker %s → CLOSED (success)", prev)

    def record_failure(self) -> None:
        self._consecutive_failures += 1

        if self._state == CBState.HALF_OPEN:
            self._trip()
            return

        if self._consecutive_failures >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        prev = self._state
        self._state = CBState.OPEN
        self._opened_at = monotonic()
        logger.warning(
            "CircuitBreaker %s → OPEN (failures=%d)",
            prev,
            self._consecutive_failures,
        )

    def reset(self) -> None:
        self._state = CBState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
