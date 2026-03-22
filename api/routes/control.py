"""Position and strategy control endpoints (embedded mode)."""

from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_exchange, get_loops
from api.middleware.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["control"], dependencies=[Depends(verify_api_key)])


# ── Request schemas ───────────────────────────────────────────────


class PositionCloseRequest(BaseModel):
    strategy_id: str = "STR-001"


class SLUpdateRequest(BaseModel):
    strategy_id: str = "STR-001"
    stop_loss: float


class TPUpdateRequest(BaseModel):
    strategy_id: str = "STR-001"
    take_profit: float


class StrategySwitchRequest(BaseModel):
    strategy_id: str  # preset ID to switch to, e.g. "STR-005"


# ── Endpoints ─────────────────────────────────────────────────────


@router.post("/position/close")
async def close_position(
    req: PositionCloseRequest,
    loops=Depends(get_loops),
    exchange=Depends(get_exchange),
):
    loop = _get_loop_or_404(loops, req.strategy_id)
    pos = loop._position_mgr.get_position(loop._strategy_id)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No open position for {req.strategy_id}")

    amount = float(pos.amount)

    try:
        # Use the same close logic as regime switch
        await loop._execute_regime_close(pos)

        return {
            "success": True,
            "message": "Position closed at market price",
            "sold_amount": str(amount),
        }
    except Exception as e:
        logger.exception("Failed to close position for %s", req.strategy_id)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/position/sl")
async def update_stop_loss(
    req: SLUpdateRequest,
    loops=Depends(get_loops),
):
    loop = _get_loop_or_404(loops, req.strategy_id)
    pos = loop._position_mgr.get_position(loop._strategy_id)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No open position for {req.strategy_id}")

    old_sl = str(pos.stop_loss) if pos.stop_loss else None
    await loop._position_mgr.set_stop_loss(loop._strategy_id, Decimal(str(req.stop_loss)))

    return {
        "success": True,
        "strategy_id": req.strategy_id,
        "old_sl": old_sl,
        "new_sl": str(req.stop_loss),
    }


@router.post("/position/tp")
async def update_take_profit(
    req: TPUpdateRequest,
    loops=Depends(get_loops),
):
    loop = _get_loop_or_404(loops, req.strategy_id)
    pos = loop._position_mgr.get_position(loop._strategy_id)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No open position for {req.strategy_id}")

    old_tp = str(pos.take_profit) if hasattr(pos, "take_profit") and pos.take_profit else None
    await loop._position_mgr.set_take_profit(loop._strategy_id, Decimal(str(req.take_profit)))

    return {
        "success": True,
        "strategy_id": req.strategy_id,
        "old_tp": old_tp,
        "new_tp": str(req.take_profit),
    }


@router.post("/strategy/switch")
async def switch_strategy(
    req: StrategySwitchRequest,
    loops=Depends(get_loops),
):
    if not loops:
        raise HTTPException(status_code=404, detail="No active trading loops")

    # Get first loop (single-strategy mode)
    sid = next(iter(loops))
    loop = loops[sid]

    old_preset = loop._regime_mgr.current_preset or sid

    preset = loop._regime_mgr.get_preset(req.strategy_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown preset: {req.strategy_id}")

    loop._signal_gen.apply_preset(preset)
    loop._regime_mgr._current_preset = req.strategy_id

    return {
        "success": True,
        "old_preset": old_preset,
        "new_preset": req.strategy_id,
        "message": f"Strategy switched from {old_preset} to {req.strategy_id}",
    }


# ── Helpers ───────────────────────────────────────────────────────


def _get_loop_or_404(loops: dict, strategy_id: str):
    """Get trading loop for strategy_id, falling back to first loop in single-strategy mode."""
    loop = loops.get(strategy_id)
    if loop is None and len(loops) == 1:
        return next(iter(loops.values()))
    if loop is None:
        raise HTTPException(status_code=404, detail=f"No loop for strategy {strategy_id}")
    return loop
