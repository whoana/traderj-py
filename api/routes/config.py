"""Config and regime status endpoints (embedded mode)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import app_state, get_loops
from api.middleware.auth import verify_api_key

router = APIRouter(tags=["config"], dependencies=[Depends(verify_api_key)])


@router.get("/config")
async def get_config(loops=Depends(get_loops)):
    settings = app_state.settings
    trading_mode = settings.trading.mode if settings else "paper"
    symbol = settings.trading.symbols[0] if settings and settings.trading.symbols else "BTC/KRW"

    # Get current preset from first loop
    current_preset = {}
    active_strategies = list(loops.keys())
    regime_switch_info = {}

    if loops:
        loop = next(iter(loops.values()))
        sig = loop._signal_gen

        current_preset = {
            "id": loop._regime_mgr.current_preset or loop._strategy_id,
            "scoring_mode": sig.scoring_mode.value if hasattr(sig.scoring_mode, "value") else str(sig.scoring_mode),
            "entry_mode": sig.entry_mode.value if hasattr(sig.entry_mode, "value") else str(sig.entry_mode),
            "buy_threshold": sig.buy_threshold,
            "sell_threshold": sig.sell_threshold,
            "tf_weights": sig.tf_weights,
            "use_daily_gate": sig.use_daily_gate,
            "macro_weight": sig.macro_weight,
        }

        mgr = loop._regime_mgr
        cfg = mgr.config
        regime_switch_info = {
            "enabled": cfg.enabled,
            "debounce_count": cfg.debounce_count,
            "cooldown_minutes": cfg.cooldown_minutes,
            "close_position_on_switch": cfg.close_position_on_switch,
            "loss_threshold_pct": cfg.loss_threshold_pct,
        }

    risk_info = {}
    if settings:
        risk_info = {
            "max_position_pct": settings.trading.max_position_pct,
            "daily_loss_limit": settings.trading.daily_loss_limit,
            "max_consecutive_losses": settings.trading.max_consecutive_losses,
        }

    return {
        "trading_mode": trading_mode,
        "symbol": symbol,
        "active_strategies": active_strategies,
        "current_preset": current_preset,
        "risk": risk_info,
        "regime_switch": regime_switch_info,
    }


@router.get("/regime")
async def get_regime(loops=Depends(get_loops)):
    if not loops:
        return {
            "current_regime": None,
            "confidence": 0.0,
            "mapped_preset": "",
            "last_switch_at": None,
            "switch_count": 0,
            "switch_locked": False,
            "pending_count": 0,
            "dca_config": None,
            "grid_config": None,
        }

    loop = next(iter(loops.values()))
    mgr = loop._regime_mgr

    # DCA config
    dca = None
    dca_cfg = mgr.get_dca_config()
    if dca_cfg:
        dca = {
            "buy_amount_krw": dca_cfg.buy_amount_krw,
            "interval_hours": dca_cfg.interval_hours,
        }

    # Grid config — needs current price
    grid = None
    grid_cfg = mgr.get_grid_config(current_price=0)  # 0 means no grid
    if grid_cfg:
        grid = {
            "grid_count": grid_cfg.grid_count,
            "lower_price": grid_cfg.lower_price,
            "upper_price": grid_cfg.upper_price,
        }

    last_switch_at = None
    confidence = 0.0
    if mgr._switch_history:
        last_switch_at = mgr._switch_history[-1].get("time")
        confidence = mgr._switch_history[-1].get("confidence", 0.0)

    return {
        "current_regime": mgr.current_regime.value if mgr.current_regime else None,
        "confidence": confidence,
        "mapped_preset": mgr.current_preset,
        "last_switch_at": last_switch_at,
        "switch_count": mgr.switch_count,
        "switch_locked": mgr.is_locked,
        "pending_count": mgr._pending_count,
        "dca_config": dca,
        "grid_config": grid,
    }
