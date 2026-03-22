"""APScheduler wrapper for cron-like job scheduling.

Provides a simple interface for registering async jobs
on cron/interval schedules within the asyncio event loop.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

AsyncJobFunc = Callable[..., Coroutine[Any, Any, None]]


class Scheduler:
    """Thin wrapper around APScheduler's AsyncIOScheduler."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._job_count = 0
        self._running = False

    def add_cron_job(
        self,
        func: AsyncJobFunc,
        *,
        hour: str | int = "*",
        minute: str | int = "0",
        second: str | int = "0",
        job_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Register a cron-based async job."""
        jid = job_id or f"cron-{self._job_count}"
        self._scheduler.add_job(
            func,
            CronTrigger(hour=str(hour), minute=str(minute), second=str(second)),
            id=jid,
            replace_existing=True,
            **kwargs,
        )
        self._job_count += 1
        logger.info("Registered cron job: %s", jid)
        return jid

    def add_interval_job(
        self,
        func: AsyncJobFunc,
        *,
        seconds: int = 60,
        job_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Register an interval-based async job."""
        jid = job_id or f"interval-{self._job_count}"
        self._scheduler.add_job(
            func,
            IntervalTrigger(seconds=seconds),
            id=jid,
            replace_existing=True,
            **kwargs,
        )
        self._job_count += 1
        logger.info("Registered interval job: %s (every %ds)", jid, seconds)
        return jid

    def start(self) -> None:
        self._scheduler.start()
        self._running = True
        logger.info("Scheduler started with %d jobs", self._job_count)

    def shutdown(self, wait: bool = False) -> None:
        self._scheduler.shutdown(wait=wait)
        self._running = False
        logger.info("Scheduler shut down")

    @property
    def job_count(self) -> int:
        return self._job_count

    @property
    def running(self) -> bool:
        return self._running
