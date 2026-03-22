"""Position and strategy control endpoints (embedded mode)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_exchange, get_loops, get_store
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
    store=Depends(get_store),
):
    # Find the loop for this strategy
    loop = _get_loop_or_404(loops, req.strategy_id)

    # Check for open position
    position = loop._pos_mgr._positions.get(req.strategy_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"No open position for {req.strategy_id}")

    amount = float(position.amount)
    symbol = position.symbol

    # Execute market sell
    try:
        ticker = await exchange.fetch_ticker(symbol)
        sell_price = float(ticker.get("last", 0))

        await loop._order_mgr.execute_sell(
            strategy_id=req.strategy_id,
            symbol=symbol,
            amount=amount,
            reason="manual_close",
        )

        return {
            "success": True,
            "message": "Position closed at market price",
            "sold_amount": str(amount),
            "sold_price": str(sell_price),
        }
    except Exception as e:
        logger.exception("Failed to close position for %s", req.strategy_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/position/sl")
async def update_stop_loss(
    req: SLUpdateRequest,
    loops=Depends(get_loops),
):
    loop = _get_loop_or_404(loops, req.strategy_id)
    position = loop._pos_mgr._positions.get(req.strategy_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"No open position for {req.strategy_id}")

    old_sl = str(position.stop_loss) if position.stop_loss else None
    loop._pos_mgr.set_stop_loss(req.strategy_id, req.stop_loss)

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
    position = loop._pos_mgr._positions.get(req.strategy_id)
    if position is None:
        raise HTTPException(status_code=404, detail=f"No open position for {req.strategy_id}")

    old_tp = str(position.take_profit) if hasattr(position, "take_profit") and position.take_profit else None
    loop._pos_mgr.set_take_profit(req.strategy_id, req.take_profit)

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
    # Apply to first (or only) active loop
    if not loops:
        raise HTTPException(status_code=404, detail="No active trading loops")

    # Get first loop (single-strategy mode)
    sid = next(iter(loops))
    loop = loops[sid]

    old_preset = loop._regime_mgr.current_preset or sid

    # Get the preset
    preset = loop._regime_mgr.get_preset(req.strategy_id)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown preset: {req.strategy_id}")

    # Apply preset
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
    """Get trading loop for strategy_id or raise 404."""
    loop = loops.get(strategy_id)
    if loop is None:
        # Try first loop if only one exists (single-strategy mode)
        if len(loops) == 1:
            return next(iter(loops.values()))
        raise HTTPException(status_code=404, detail=f"No loop for strategy {strategy_id}")
    return loop
