"""Sliding window rate limiter for exchange API calls.

Limits requests per time window to comply with Upbit API rate limits:
- Public API: 600 req/min (10/sec)
- Private API: 120 req/min (2/sec)
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class SlidingWindowRateLimiter:
    """Token-bucket style sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        async with self._lock:
            now = time.monotonic()
            # Remove timestamps outside the window
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max:
                # Wait until oldest timestamp expires
                wait_time = self._timestamps[0] + self._window - now
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                self._timestamps.popleft()

            self._timestamps.append(time.monotonic())

    @property
    def available(self) -> int:
        """Number of available request slots."""
        now = time.monotonic()
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        return max(0, self._max - len(self._timestamps))
