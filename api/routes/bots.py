"""Bot management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_engine, get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import BotControlResponse, BotResponse

router = APIRouter(prefix="/bots", tags=["bots"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=list[BotResponse])
async def list_bots(store=Depends(get_store)):
    bots = []
    # Get all known strategy IDs from bot_state table
    for sid in await _get_all_strategy_ids(store):
        model = await store.get_bot_state(sid)
        if model:
            bots.append(BotResponse(
                strategy_id=model.strategy_id,
                state=model.state,
                trading_mode=model.trading_mode,
                updated_at=model.last_updated,
            ))
    return bots


@router.get("/{strategy_id}", response_model=BotResponse)
async def get_bot(strategy_id: str, store=Depends(get_store)):
    model = await store.get_bot_state(strategy_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Bot {strategy_id} not found")
    return BotResponse(
        strategy_id=model.strategy_id,
        state=model.state,
        trading_mode=model.trading_mode,
        updated_at=model.last_updated,
    )


@router.post("/{strategy_id}/start", response_model=BotControlResponse)
async def start_bot(strategy_id: str, engine=Depends(get_engine)):
    return await _send_bot_command(engine, strategy_id, "start")


@router.post("/{strategy_id}/stop", response_model=BotControlResponse)
async def stop_bot(strategy_id: str, engine=Depends(get_engine)):
    return await _send_bot_command(engine, strategy_id, "stop")


@router.post("/{strategy_id}/pause", response_model=BotControlResponse)
async def pause_bot(strategy_id: str, engine=Depends(get_engine)):
    return await _send_bot_command(engine, strategy_id, "pause")


@router.post("/{strategy_id}/resume", response_model=BotControlResponse)
async def resume_bot(strategy_id: str, engine=Depends(get_engine)):
    return await _send_bot_command(engine, strategy_id, "start")  # resume = start from paused


@router.post("/{strategy_id}/emergency-exit", response_model=BotControlResponse)
async def emergency_exit(strategy_id: str, engine=Depends(get_engine)):
    return await _send_bot_command(engine, strategy_id, "emergency_exit")


@router.post("/emergency-stop", response_model=BotControlResponse)
async def emergency_stop_all(engine=Depends(get_engine)):
    return await _send_bot_command(engine, "__all__", "emergency_stop")


# ── Helpers ──────────────────────────────────────────────────────────


async def _send_bot_command(engine, strategy_id: str, action: str) -> BotControlResponse:
    if engine is None:
        return BotControlResponse(
            strategy_id=strategy_id,
            action=action,
            success=False,
            message="Engine not connected",
        )
    try:
        await engine.send_command(strategy_id, action)
        return BotControlResponse(
            strategy_id=strategy_id,
            action=action,
            success=True,
            message=f"{action} command sent",
        )
    except Exception as e:
        return BotControlResponse(
            strategy_id=strategy_id,
            action=action,
            success=False,
            message=str(e),
        )


async def _get_all_strategy_ids(store) -> list[str]:
    """Get all known strategy IDs. Uses pending commands as a fallback discovery."""
    # Phase 3: simple approach — check known bot states
    # In production, could use a dedicated strategy registry
    commands = await store.get_pending_commands()
    ids = set()
    for cmd in commands:
        ids.add(cmd.strategy_id)
    # Also check for any bot state entries
    for sid in list(ids) or ["STR-001"]:
        model = await store.get_bot_state(sid)
        if model:
            ids.add(model.strategy_id)
    return list(ids)
