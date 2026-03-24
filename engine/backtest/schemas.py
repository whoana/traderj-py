"""Pydantic models for dashboard backtest API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BacktestMode(StrEnum):
    SINGLE = "single"
    COMPARE = "compare"
    AI_REGIME = "ai_regime"


class BacktestJobStatus(StrEnum):
    PENDING = "pending"
    FETCHING = "fetching"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Request Models ───────────────────────────────────────────


class BacktestRunRequest(BaseModel):
    mode: BacktestMode
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    strategy_id: str | None = None  # required for mode=single
    initial_balance: float = 50_000_000


# ── Response Models ──────────────────────────────────────────


class BacktestJobResponse(BaseModel):
    job_id: str
    status: BacktestJobStatus
    mode: BacktestMode
    progress: str = ""
    elapsed_sec: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class BacktestJobSummary(BaseModel):
    job_id: str
    mode: BacktestMode
    status: BacktestJobStatus
    start_date: str
    end_date: str
    created_at: str
    summary: dict[str, Any] | None = None


class BacktestJobListResponse(BaseModel):
    jobs: list[BacktestJobSummary]
