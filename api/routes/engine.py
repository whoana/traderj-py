"""Engine status and control endpoints (embedded mode)."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from api.deps import app_state, get_loops
from api.middleware.auth import verify_api_key

router = APIRouter(prefix="/engine", tags=["engine"], dependencies=[Depends(verify_api_key)])

_start_time = time.time()


@router.get("/status")
async def engine_status(loops=Depends(get_loops)):
    strategies = []
    regime_info = None

    for sid, loop in loops.items():
        has_position = bool(loop._position_mgr._positions)
        strategies.append({
            "strategy_id": sid,
            "preset": loop._regime_mgr.current_preset or sid,
            "state": loop._state.state.value if hasattr(loop._state, "state") else "unknown",
            "last_tick_at": None,
            "tick_count": loop._tick_count,
            "has_open_position": has_position,
            "running": loop._running,
        })

        # Regime info from first loop
        if regime_info is None and hasattr(loop, "_regime_mgr"):
            mgr = loop._regime_mgr
            regime_info = {
                "current": mgr.current_regime.value if mgr.current_regime else None,
                "confidence": 0.0,
                "mapped_preset": mgr.current_preset,
                "last_switch_at": None,
                "switch_count": mgr.switch_count,
                "locked": mgr.is_locked,
            }
            if mgr._switch_history:
                regime_info["last_switch_at"] = mgr._switch_history[-1].get("time")
                regime_info["confidence"] = mgr._switch_history[-1].get("confidence", 0.0)

    is_running = any(loop._running for loop in loops.values())

    return {
        "status": "running" if is_running else "stopped",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "trading_mode": "paper",
        "strategies": strategies,
        "regime": regime_info,
    }


@router.post("/stop")
async def engine_stop(loops=Depends(get_loops)):
    stopped = []
    for sid, loop in loops.items():
        if loop._running:
            await loop.stop()
            stopped.append(sid)

    return {
        "success": True,
        "message": f"Stopped {len(stopped)} trading loop(s)",
        "stopped_strategies": stopped,
    }


@router.post("/start")
async def engine_start(loops=Depends(get_loops)):
    started = []
    for sid, loop in loops.items():
        if not loop._running:
            await loop.start()
            started.append(sid)

    return {
        "success": True,
        "message": f"Started {len(started)} trading loop(s)",
        "started_strategies": started,
    }


@router.post("/restart")
async def engine_restart(loops=Depends(get_loops)):
    restarted = []
    for sid, loop in loops.items():
        if loop._running:
            await loop.stop()
        await loop.start()
        restarted.append(sid)

    return {
        "success": True,
        "message": f"Restarted {len(restarted)} trading loop(s)",
        "restarted_strategies": restarted,
    }
