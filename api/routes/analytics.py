"""Analytics endpoints — PnL analytics and strategy comparison."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from api.deps import get_store
from api.middleware.auth import verify_api_key

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(verify_api_key)])


@router.get("/pnl")
async def get_pnl_analytics(
    strategy_id: str,
    days: int = Query(30, ge=1, le=365),
    store=Depends(get_store),
):
    """Cumulative PnL and equity curve for a strategy."""
    end = date.today()
    start = end - timedelta(days=days)
    records = await store.get_daily_pnl(strategy_id=strategy_id, start_date=start, end_date=end)

    cumulative = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    curve = []

    for r in records:
        cumulative += r.realized
        if cumulative > peak:
            peak = cumulative
        drawdown = peak - cumulative
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        curve.append({
            "date": str(r.date),
            "daily_pnl": str(r.realized),
            "cumulative_pnl": str(cumulative),
            "drawdown": str(drawdown),
            "trade_count": r.trade_count,
        })

    return {
        "strategy_id": strategy_id,
        "days": days,
        "total_pnl": str(cumulative),
        "max_drawdown": str(max_drawdown),
        "peak_pnl": str(peak),
        "total_trades": sum(r.trade_count for r in records),
        "curve": curve,
    }


@router.get("/compare")
async def compare_strategies(
    strategy_ids: str = Query(..., description="Comma-separated strategy IDs"),
    days: int = Query(30, ge=1, le=365),
    store=Depends(get_store),
):
    """Compare PnL performance across strategies."""
    ids = [s.strip() for s in strategy_ids.split(",") if s.strip()]
    end = date.today()
    start = end - timedelta(days=days)

    results = []
    for sid in ids:
        records = await store.get_daily_pnl(strategy_id=sid, start_date=start, end_date=end)
        total_pnl = sum((r.realized for r in records), Decimal("0"))
        total_trades = sum(r.trade_count for r in records)

        # Simple Sharpe approximation (daily returns)
        daily_returns = [float(r.realized) for r in records]
        if len(daily_returns) > 1:
            import statistics

            mean_ret = statistics.mean(daily_returns)
            std_ret = statistics.stdev(daily_returns) or 1.0
            sharpe = (mean_ret / std_ret) * (252**0.5)  # annualized
        else:
            sharpe = 0.0

        results.append({
            "strategy_id": sid,
            "total_pnl": str(total_pnl),
            "total_trades": total_trades,
            "avg_daily_pnl": str(total_pnl / max(len(records), 1)),
            "sharpe_ratio": round(sharpe, 3),
            "trading_days": len(records),
        })

    return {"days": days, "strategies": results}
