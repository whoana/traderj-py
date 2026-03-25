"""Wizard API endpoints for the profit improvement process.

4 endpoints:
  - POST /backtest/wizard/optimize      — run Optuna optimization with improved objective
  - POST /backtest/wizard/validate      — Gate 1 walk-forward validation
  - POST /backtest/wizard/apply         — apply changes (JSON override + regime map)
  - GET  /backtest/wizard/apply-preview — before/after comparison preview
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import app_state
from api.middleware.auth import verify_api_key
from api.routes.backtest import _manager
from engine.backtest.job_manager import BacktestJob
from engine.backtest.schemas import BacktestJobStatus, BacktestMode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest/wizard", tags=["wizard"], dependencies=[Depends(verify_api_key)])


def _get_db_path() -> str:
    store = app_state.data_store
    if store is None:
        return ":memory:"
    db_path = getattr(store, "_db_path", None)
    if db_path and db_path != ":memory:":
        return db_path
    return ":memory:"


# ── Request/Response Models ─────────────────────────────────


class WizardOptimizeRequest(BaseModel):
    strategy_id: str
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    n_trials: int = Field(30, ge=10, le=100)
    initial_balance: float = 50_000_000


class WizardValidateRequest(BaseModel):
    strategy_id: str
    params: dict[str, float]
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    baseline_metrics: dict[str, Any] | None = None
    initial_balance: float = 50_000_000


class WizardApplyRequest(BaseModel):
    changes: dict[str, Any]
    validation_job_id: str | None = None
    skip_validation: bool = False


class WizardApplyPreviewQuery(BaseModel):
    strategy_id: str
    params: dict[str, float] = Field(default_factory=dict)
    regime_map: dict[str, str] = Field(default_factory=dict)


class JobResponse(BaseModel):
    job_id: str
    status: str
    result: dict[str, Any] | None = None


# ── Endpoints ───────────────────────────────────────────────


@router.post("/optimize", response_model=JobResponse)
async def wizard_optimize(req: WizardOptimizeRequest):
    """Run Optuna optimization with risk-adjusted composite objective."""
    from engine.strategy.presets import STRATEGY_PRESETS

    if req.strategy_id not in STRATEGY_PRESETS:
        valid = [sid for sid in STRATEGY_PRESETS if sid != "default"]
        raise HTTPException(400, f"Unknown strategy. Valid: {valid}")

    start = datetime.strptime(req.start_date, "%Y-%m-%d")
    end = datetime.strptime(req.end_date, "%Y-%m-%d")
    days = (end - start).days + 1
    if days < 14:
        raise HTTPException(400, "Minimum optimization period is 14 days")

    config = {
        "strategy_id": req.strategy_id,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "initial_balance": req.initial_balance,
        "n_trials": req.n_trials,
    }

    from engine.backtest.runners import run_optimize

    db_path = _get_db_path()

    async def runner(job: BacktestJob, update):
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            return await run_optimize(job, update, db)

    try:
        job = await _manager.submit(BacktestMode.OPTIMIZE, config, runner)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from None

    return JobResponse(job_id=job.job_id, status=job.status.value)


@router.post("/validate", response_model=JobResponse)
async def wizard_validate(req: WizardValidateRequest):
    """Run Gate 1 walk-forward validation on candidate parameters."""
    import asyncio

    from engine.backtest.candle_cache import CandleCache
    from engine.backtest.runners import _fetch_all_candles
    from engine.backtest.validators import run_gate1_validation
    from engine.strategy.presets import STRATEGY_PRESETS, load_preset

    if req.strategy_id not in STRATEGY_PRESETS:
        raise HTTPException(400, f"Unknown strategy: {req.strategy_id}")

    start = datetime.strptime(req.start_date, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(req.end_date, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=UTC,
    )

    preset = load_preset(req.strategy_id)
    primary_tf = max(preset.tf_weights, key=preset.tf_weights.get)

    config = {
        "strategy_id": req.strategy_id,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "params": req.params,
    }

    db_path = _get_db_path()

    async def runner(job: BacktestJob, update):
        update("Fetching OHLCV data...")
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cache = CandleCache(db)
            await cache.init_table()
            ohlcv, _ = await _fetch_all_candles(cache, start, end, update)

        update("Running walk-forward validation...")
        baseline = req.baseline_metrics or {}
        result = await asyncio.to_thread(
            run_gate1_validation,
            preset,
            req.params,
            ohlcv,
            baseline,
            req.initial_balance,
            primary_tf,
        )
        return {"validation": result.to_dict()}

    try:
        job = await _manager.submit(BacktestMode.SINGLE, config, runner)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from None

    return JobResponse(job_id=job.job_id, status=job.status.value)


@router.get("/validate/{job_id}", response_model=JobResponse)
async def get_validation_result(job_id: str):
    """Get validation job status and result."""
    job = _manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return JobResponse(
        job_id=job.job_id,
        status=job.status.value,
        result=job.result if job.status == BacktestJobStatus.DONE else None,
    )


@router.post("/apply")
async def wizard_apply(req: WizardApplyRequest):
    """Apply optimized changes — save JSON overrides and optionally update regime map."""
    from engine.strategy.preset_override import save_override, save_regime_map
    from engine.strategy.presets import STRATEGY_PRESETS

    changes = req.changes
    applied: list[str] = []

    # Validate strategy references
    param_optimize = changes.get("param_optimize", {})
    strategy_switch = changes.get("strategy_switch", {})
    regime_map_changes = changes.get("regime_map", {})

    target_strategy = strategy_switch.get("to") or strategy_switch.get("from")

    # Apply param overrides
    if param_optimize and target_strategy:
        if target_strategy not in STRATEGY_PRESETS:
            raise HTTPException(400, f"Unknown strategy: {target_strategy}")
        save_override(target_strategy, param_optimize)
        applied.append("param_optimize")
        logger.info("Applied param overrides for %s: %s", target_strategy, param_optimize)

    # Apply regime map changes
    if regime_map_changes:
        for _regime, strategy_id in regime_map_changes.items():
            if strategy_id not in STRATEGY_PRESETS:
                raise HTTPException(400, f"Unknown strategy in regime_map: {strategy_id}")
        save_regime_map(regime_map_changes)
        applied.append("regime_map")
        logger.info("Applied regime map changes: %s", regime_map_changes)

    # Strategy switch is handled via regime map or direct preset change
    if strategy_switch:
        applied.append("strategy_switch")

    tuning_id = f"tun-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    monitoring_until = datetime.now(tz=UTC) + timedelta(hours=48)

    return {
        "applied": applied,
        "override_file": "/data/preset_overrides.json",
        "tuning_id": tuning_id,
        "monitoring_until": monitoring_until.isoformat(),
    }


@router.get("/apply-preview")
async def wizard_apply_preview(strategy_id: str, params: str = ""):
    """Preview before/after parameter comparison.

    Query params:
      - strategy_id: target strategy
      - params: comma-separated key=value pairs (e.g., "buy_threshold=0.15,macro_weight=0.3")
    """
    from engine.strategy.presets import STRATEGY_PRESETS, _apply_overrides, load_preset

    if strategy_id not in STRATEGY_PRESETS:
        raise HTTPException(400, f"Unknown strategy: {strategy_id}")

    # Parse params from query string
    param_dict: dict[str, float] = {}
    if params:
        for pair in params.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                try:
                    param_dict[k.strip()] = float(v.strip())
                except ValueError:
                    raise HTTPException(400, f"Invalid param value: {pair}") from None

    base = STRATEGY_PRESETS[strategy_id]
    current = load_preset(strategy_id)
    candidate = _apply_overrides(current, param_dict) if param_dict else current

    def _preset_snapshot(p):
        return {
            "buy_threshold": p.buy_threshold,
            "sell_threshold": p.sell_threshold,
            "macro_weight": p.macro_weight,
            "tf_weights": dict(p.tf_weights),
            "score_weights": {"w1": p.score_weights.w1, "w2": p.score_weights.w2, "w3": p.score_weights.w3},
        }

    return {
        "strategy_id": strategy_id,
        "strategy_name": base.name,
        "default": _preset_snapshot(base),
        "current": _preset_snapshot(current),
        "candidate": _preset_snapshot(candidate),
        "changes": {k: {"from": getattr(current, k, None), "to": v} for k, v in param_dict.items() if hasattr(current, k)},
    }
