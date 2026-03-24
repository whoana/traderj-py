"""AI Tuner REST API endpoints.

7 endpoints for tuning management:
  - GET  /tuning/history         — list tuning history
  - GET  /tuning/history/{id}    — tuning detail
  - POST /tuning/rollback/{id}   — manual rollback
  - GET  /tuning/status          — tuner state overview
  - GET  /tuning/provider-status — LLM provider health
  - POST /tuning/trigger/{sid}   — manual trigger
  - POST /tuning/approve/{id}    — Tier 3 approval
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import app_state, get_store
from api.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tuning", tags=["tuning"], dependencies=[Depends(verify_api_key)])


def _get_pipeline():
    """Get TunerPipeline from app state."""
    pipeline = app_state.tuner_pipeline
    if pipeline is None:
        raise HTTPException(status_code=503, detail="AI Tuner not enabled")
    return pipeline


def _get_tuner_store():
    """Get TunerStore from pipeline."""
    pipeline = _get_pipeline()
    return pipeline._store


def _get_provider_router():
    """Get ProviderRouter from evaluator."""
    pipeline = _get_pipeline()
    return pipeline._evaluator._router


# ── Response helpers ─────────────────────────────────────────────


def _record_to_dict(record) -> dict[str, Any]:
    """Convert TuningHistoryRecord to API response dict."""
    return {
        "tuning_id": record.tuning_id,
        "created_at": record.created_at.isoformat(),
        "strategy_id": record.strategy_id,
        "status": record.status.value if hasattr(record.status, "value") else str(record.status),
        "reason": record.reason,
        "changes": [
            {
                "parameter_name": c.parameter_name,
                "tier": c.tier.value if hasattr(c.tier, "value") else str(c.tier),
                "old_value": c.old_value,
                "new_value": c.new_value,
                "change_pct": c.change_pct,
            }
            for c in record.changes
        ],
        "eval_metrics": {
            "win_rate": record.eval_metrics.win_rate,
            "profit_factor": record.eval_metrics.profit_factor,
            "max_drawdown": record.eval_metrics.max_drawdown,
            "eval_window": record.eval_metrics.eval_window,
        },
        "validation_pf": record.validation_pf,
        "validation_mdd": record.validation_mdd,
        "llm_provider": record.llm_provider.value if hasattr(record.llm_provider, "value") else str(record.llm_provider),
        "llm_model": record.llm_model,
        "llm_confidence": record.llm_confidence.value if record.llm_confidence and hasattr(record.llm_confidence, "value") else None,
    }


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/history")
async def get_tuning_history(
    strategy_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """List tuning history records."""
    from engine.tuner.enums import TuningStatus

    store = _get_tuner_store()
    status_enum = TuningStatus(status) if status else None
    records = await store.get_tuning_history(
        strategy_id=strategy_id,
        status=status_enum,
        limit=limit,
    )
    return [_record_to_dict(r) for r in records]


@router.get("/history/{tuning_id}")
async def get_tuning_detail(tuning_id: str) -> dict:
    """Get detailed tuning session info."""
    store = _get_tuner_store()
    records = await store.get_tuning_history(limit=200)
    for r in records:
        if r.tuning_id == tuning_id:
            return _record_to_dict(r)
    raise HTTPException(status_code=404, detail=f"Tuning session {tuning_id} not found")


@router.post("/rollback/{tuning_id}")
async def manual_rollback(tuning_id: str) -> dict:
    """Manually rollback a tuning session."""
    pipeline = _get_pipeline()
    success = await pipeline.manual_rollback(tuning_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Rollback failed for {tuning_id}")
    return {"status": "rolled_back", "tuning_id": tuning_id}


@router.get("/status")
async def get_tuner_status() -> dict:
    """Get AI Tuner overall status."""
    pipeline = _get_pipeline()
    store = _get_tuner_store()

    monitoring = await store.get_monitoring_sessions()
    latest_records: dict[str, Any] = {}
    for sid in pipeline._strategies:
        latest = await store.get_latest_tuning(sid)
        if latest:
            latest_records[sid] = _record_to_dict(latest)

    return {
        "state": pipeline.state.value if hasattr(pipeline.state, "value") else str(pipeline.state),
        "active_monitoring": [
            {"tuning_id": r.tuning_id, "strategy_id": r.strategy_id}
            for r in monitoring
        ],
        "consecutive_rollbacks": pipeline._rollback.consecutive_rollback_count,
        "registered_strategies": list(pipeline._strategies.keys()),
        "latest_tuning": latest_records,
    }


@router.get("/provider-status")
async def get_provider_status() -> dict:
    """Get LLM provider health and budget status."""
    try:
        provider_router = _get_provider_router()
        return provider_router.get_provider_status()
    except Exception:
        return {"error": "Provider status unavailable"}


class TriggerRequest(BaseModel):
    tier: str = "tier_1"


@router.post("/trigger/{strategy_id}")
async def trigger_tuning(strategy_id: str, req: TriggerRequest = TriggerRequest()) -> dict:
    """Manually trigger a tuning session (debugging)."""
    from engine.tuner.enums import TierLevel

    pipeline = _get_pipeline()
    if strategy_id not in pipeline._strategies:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not registered")

    try:
        tier = TierLevel(req.tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {req.tier}")

    result = await pipeline.run_tuning_session(strategy_id, tier)
    return {
        "tuning_id": result.tuning_id,
        "strategy_id": result.strategy_id,
        "tier": result.tier.value if hasattr(result.tier, "value") else str(result.tier),
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "reason": result.reason,
        "changes_count": len(result.changes),
    }


class ApproveRequest(BaseModel):
    approved: bool = True


@router.post("/approve/{tuning_id}")
async def approve_tier3_change(tuning_id: str, req: ApproveRequest = ApproveRequest()) -> dict:
    """Approve or reject a Tier 3 pending change."""
    pipeline = _get_pipeline()
    success = await pipeline.approve_tier3(tuning_id, req.approved)
    if not success:
        raise HTTPException(status_code=404, detail=f"Pending tuning {tuning_id} not found")
    return {
        "tuning_id": tuning_id,
        "action": "approved" if req.approved else "rejected",
    }
