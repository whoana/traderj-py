"""Dashboard Backtest REST API endpoints.

5 endpoints:
  - POST /backtest/run          — start a backtest job
  - GET  /backtest/jobs/{id}    — job status / result
  - GET  /backtest/jobs         — job history list
  - DELETE /backtest/jobs/{id}  — cancel a running job
  - GET  /backtest/results      — saved backtest results from DB
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import app_state, get_store
from api.middleware.auth import verify_api_key
from engine.backtest.job_manager import BacktestJob, BacktestJobManager
from engine.backtest.schemas import (
    BacktestJobListResponse,
    BacktestJobResponse,
    BacktestJobStatus,
    BacktestJobSummary,
    BacktestMode,
    BacktestRunRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"], dependencies=[Depends(verify_api_key)])

# Singleton job manager — lives in module scope
_manager = BacktestJobManager()


def _get_db_path() -> str:
    """Get SQLite DB path for candle cache."""
    store = app_state.data_store
    if store is None:
        return ":memory:"
    db_path = getattr(store, "_db_path", None)
    if db_path and db_path != ":memory:":
        return db_path
    return ":memory:"


def _job_to_response(job: BacktestJob) -> BacktestJobResponse:
    return BacktestJobResponse(
        job_id=job.job_id,
        status=job.status,
        mode=job.mode,
        progress=job.progress,
        elapsed_sec=round(job.elapsed_sec, 1),
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        error=job.error,
        result=job.result if job.status == BacktestJobStatus.DONE else None,
    )


def _job_to_summary(job: BacktestJob) -> BacktestJobSummary:
    return BacktestJobSummary(
        job_id=job.job_id,
        mode=job.mode,
        status=job.status,
        start_date=job.config.get("start_date", ""),
        end_date=job.config.get("end_date", ""),
        created_at=job.created_at.isoformat(),
        summary=job.summary,
    )


# ── Endpoints ────────────────────────────────────────────────


@router.post("/run", response_model=BacktestJobResponse)
async def run_backtest(req: BacktestRunRequest):
    """Start a new backtest job."""
    # Validate
    if req.mode == BacktestMode.SINGLE and not req.strategy_id:
        raise HTTPException(400, "strategy_id is required for single mode")

    start = datetime.strptime(req.start_date, "%Y-%m-%d")
    end = datetime.strptime(req.end_date, "%Y-%m-%d")
    days = (end - start).days + 1
    if days < 7:
        raise HTTPException(400, "Minimum period is 7 days")
    if days > 180:
        raise HTTPException(400, "Maximum period is 180 days")
    if end > datetime.now():
        raise HTTPException(400, "End date cannot be in the future")

    from engine.strategy.presets import STRATEGY_PRESETS

    if req.mode == BacktestMode.SINGLE and req.strategy_id not in STRATEGY_PRESETS:
        valid = [sid for sid in STRATEGY_PRESETS if sid != "default"]
        raise HTTPException(400, f"Unknown strategy. Valid: {valid}")

    config = {
        "start_date": req.start_date,
        "end_date": req.end_date,
        "initial_balance": req.initial_balance,
    }
    if req.strategy_id:
        config["strategy_id"] = req.strategy_id

    # Select runner
    from engine.backtest.runners import run_ai_regime, run_compare, run_single

    runners = {
        BacktestMode.SINGLE: run_single,
        BacktestMode.COMPARE: run_compare,
        BacktestMode.AI_REGIME: run_ai_regime,
    }
    runner_fn = runners[req.mode]

    # Wrap runner to inject DB connection
    db_path = _get_db_path()

    async def wrapped_runner(job: BacktestJob, update):
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            return await runner_fn(job, update, db)

    try:
        job = await _manager.submit(req.mode, config, wrapped_runner)
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    return _job_to_response(job)


@router.get("/jobs/{job_id}", response_model=BacktestJobResponse)
async def get_job(job_id: str):
    """Get backtest job status and result."""
    job = _manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return _job_to_response(job)


@router.get("/jobs", response_model=BacktestJobListResponse)
async def list_jobs(limit: int = Query(10, ge=1, le=50)):
    """List recent backtest jobs."""
    jobs = _manager.list_jobs(limit)
    return BacktestJobListResponse(jobs=[_job_to_summary(j) for j in jobs])


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running backtest job."""
    job = _manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    cancelled = await _manager.cancel(job_id)
    return {"cancelled": cancelled, "job_id": job_id}


@router.get("/analyze/{job_id}")
async def analyze_job(job_id: str):
    """Analyze a completed backtest job and return actionable insights."""
    from engine.backtest.analyzer import analyze_regime_mapping, analyze_results

    job = _manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.status != BacktestJobStatus.DONE or job.result is None:
        raise HTTPException(400, "Job not completed yet")

    summary = analyze_results(job.result)
    regime_suggestions = (
        analyze_regime_mapping(job.result)
        if job.result.get("mode") == "ai_regime"
        else []
    )

    return {
        "job_id": job_id,
        "analysis": summary,
        "regime_suggestions": regime_suggestions,
    }
