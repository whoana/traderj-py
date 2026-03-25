"""In-memory backtest job manager — creates, tracks, and cancels async backtest jobs."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from engine.backtest.schemas import BacktestJobStatus, BacktestMode

logger = logging.getLogger(__name__)

MAX_HISTORY = 20
JOB_TIMEOUT_SEC = 600


@dataclass
class BacktestJob:
    job_id: str
    mode: BacktestMode
    config: dict[str, Any]
    status: BacktestJobStatus = BacktestJobStatus.PENDING
    progress: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def elapsed_sec(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or datetime.now(tz=timezone.utc)
        return (end - self.started_at).total_seconds()

    @property
    def summary(self) -> dict[str, Any] | None:
        if self.result is None:
            return None
        r = self.result
        if self.mode == BacktestMode.COMPARE:
            ranking = r.get("ranking", [])
            strategies = r.get("strategies", [])
            best = strategies[0] if strategies else {}
            return {
                "best_strategy": ranking[0] if ranking else None,
                "best_return_pct": best.get("metrics", {}).get("total_return_pct"),
            }
        if self.mode == BacktestMode.AI_REGIME:
            ai = r.get("ai_regime", {})
            return {
                "ai_return_pct": ai.get("aggregate_metrics", {}).get("total_return_pct"),
                "best_strategy": r.get("ranking", [None])[0],
            }
        if self.mode == BacktestMode.OPTIMIZE:
            opt = r.get("optimization", {})
            candidates = opt.get("candidates", [])
            best = candidates[0] if candidates else {}
            return {
                "strategy_id": opt.get("strategy_id"),
                "best_return_pct": best.get("return_pct"),
                "baseline_return_pct": opt.get("baseline", {}).get("return_pct"),
                "n_trials": opt.get("study_stats", {}).get("n_trials"),
            }
        # single
        strats = r.get("strategies", [])
        if strats:
            m = strats[0].get("metrics", {})
            return {"return_pct": m.get("total_return_pct"), "trades": m.get("total_trades")}
        return None


class BacktestJobManager:
    """Manages at most one running backtest job with history."""

    def __init__(self) -> None:
        self._jobs: OrderedDict[str, BacktestJob] = OrderedDict()
        self._current: str | None = None

    async def submit(
        self,
        mode: BacktestMode,
        config: dict[str, Any],
        runner: Callable[[BacktestJob, Callable[[str], None]], Coroutine[Any, Any, dict[str, Any]]],
    ) -> BacktestJob:
        if self._current is not None:
            cur = self._jobs.get(self._current)
            if cur and cur.status in (BacktestJobStatus.PENDING, BacktestJobStatus.FETCHING, BacktestJobStatus.RUNNING):
                raise RuntimeError("A backtest is already running")

        job_id = f"bt-{datetime.now(tz=timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        job = BacktestJob(job_id=job_id, mode=mode, config=config)
        self._jobs[job_id] = job
        self._current = job_id

        # Trim old jobs
        while len(self._jobs) > MAX_HISTORY:
            oldest_key = next(iter(self._jobs))
            old = self._jobs[oldest_key]
            if old._task and not old._task.done():
                break
            del self._jobs[oldest_key]

        job._task = asyncio.create_task(self._run(job, runner))
        return job

    async def _run(
        self,
        job: BacktestJob,
        runner: Callable[[BacktestJob, Callable[[str], None]], Coroutine[Any, Any, dict[str, Any]]],
    ) -> None:
        def update_progress(msg: str) -> None:
            job.progress = msg

        job.status = BacktestJobStatus.FETCHING
        job.started_at = datetime.now(tz=timezone.utc)

        try:
            result = await asyncio.wait_for(runner(job, update_progress), timeout=JOB_TIMEOUT_SEC)
            job.result = result
            job.status = BacktestJobStatus.DONE
        except asyncio.TimeoutError:
            job.error = f"Timeout after {JOB_TIMEOUT_SEC}s"
            job.status = BacktestJobStatus.FAILED
        except asyncio.CancelledError:
            job.status = BacktestJobStatus.CANCELLED
        except Exception as e:
            logger.exception("Backtest job %s failed", job.job_id)
            job.error = str(e)
            job.status = BacktestJobStatus.FAILED
        finally:
            job.finished_at = datetime.now(tz=timezone.utc)

    def get(self, job_id: str) -> BacktestJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 10) -> list[BacktestJob]:
        jobs = list(self._jobs.values())
        jobs.reverse()
        return jobs[:limit]

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job._task and not job._task.done():
            job._task.cancel()
            return True
        return False
