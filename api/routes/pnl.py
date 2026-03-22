"""PnL endpoints — daily and summary."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from api.deps import get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import DailyPnLResponse, PnLSummaryResponse

router = APIRouter(prefix="/pnl", tags=["pnl"], dependencies=[Depends(verify_api_key)])


@router.get("/daily", response_model=list[DailyPnLResponse])
async def get_daily_pnl(
    strategy_id: str,
    days: int = Query(30, ge=1, le=365),
    store=Depends(get_store),
):
    end = date.today()
    start = end - timedelta(days=days)
    records = await store.get_daily_pnl(
        strategy_id=strategy_id, start_date=start, end_date=end
    )
    return [
        DailyPnLResponse(
            date=str(r.date),
            strategy_id=r.strategy_id,
            realized=str(r.realized),
            unrealized=str(r.unrealized),
            trade_count=r.trade_count,
        )
        for r in records
    ]


@router.get("/summary", response_model=list[PnLSummaryResponse])
async def get_pnl_summary(
    strategy_id: str | None = None,
    store=Depends(get_store),
):
    """Simple summary — aggregates from daily PnL."""
    # Get all daily records
    records = await store.get_daily_pnl(strategy_id=strategy_id or "")
    if not records:
        return []

    # Aggregate by strategy
    from collections import defaultdict

    by_strategy: dict[str, list] = defaultdict(list)
    for r in records:
        by_strategy[r.strategy_id].append(r)

    summaries = []
    for sid, daily in by_strategy.items():
        total_realized = sum(r.realized for r in daily)
        total_trades = sum(r.trade_count for r in daily)
        summaries.append(
            PnLSummaryResponse(
                strategy_id=sid,
                total_realized=str(total_realized),
                total_trades=total_trades,
                win_rate=0.0,  # requires trade-level data
                avg_pnl=str(total_realized / max(total_trades, 1)),
                max_drawdown="0",  # requires equity curve
            )
        )
    return summaries
