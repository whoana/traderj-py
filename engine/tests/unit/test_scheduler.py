"""Unit tests for Scheduler wrapper."""

from __future__ import annotations

import asyncio

from engine.loop.scheduler import Scheduler


class TestScheduler:
    def test_initial_state(self) -> None:
        s = Scheduler()
        assert s.job_count == 0
        assert not s.running

    def test_add_cron_job(self) -> None:
        s = Scheduler()
        jid = s.add_cron_job(self._noop, hour="*", minute="0", job_id="test-cron")
        assert jid == "test-cron"
        assert s.job_count == 1

    def test_add_interval_job(self) -> None:
        s = Scheduler()
        jid = s.add_interval_job(self._noop, seconds=30, job_id="test-interval")
        assert jid == "test-interval"
        assert s.job_count == 1

    def test_auto_generated_ids(self) -> None:
        s = Scheduler()
        jid1 = s.add_cron_job(self._noop, hour="0")
        jid2 = s.add_interval_job(self._noop, seconds=60)
        assert jid1 == "cron-0"
        assert jid2 == "interval-1"

    async def test_start_and_shutdown(self) -> None:
        s = Scheduler()
        s.add_interval_job(self._noop, seconds=3600, job_id="long-job")
        s.start()
        assert s.running
        s.shutdown()
        assert not s.running

    async def test_job_fires(self) -> None:
        """Verify a short-interval job actually fires."""
        results: list[str] = []

        async def collector() -> None:
            results.append("fired")

        s = Scheduler()
        s.add_interval_job(collector, seconds=1, job_id="quick")
        s.start()

        await asyncio.sleep(1.5)
        s.shutdown()

        assert len(results) >= 1

    @staticmethod
    async def _noop() -> None:
        pass
