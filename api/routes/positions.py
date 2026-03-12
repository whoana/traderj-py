"""Position endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import PaginatedResponse, PositionResponse

router = APIRouter(prefix="/positions", tags=["positions"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=PaginatedResponse[PositionResponse])
async def list_positions(
    strategy_id: str | None = None,
    status: str | None = Query(None, pattern="^(open|closed)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    store=Depends(get_store),
):
    positions = await store.get_positions(strategy_id=strategy_id, status=status)
    total = len(positions)
    start = (page - 1) * size
    items = positions[start : start + size]

    return PaginatedResponse(
        items=[
            PositionResponse(
                id=p.id,
                symbol=p.symbol,
                side=p.side,
                entry_price=str(p.entry_price),
                amount=str(p.amount),
                current_price=str(p.current_price),
                stop_loss=str(p.stop_loss) if p.stop_loss else None,
                unrealized_pnl=str(p.unrealized_pnl),
                realized_pnl=str(p.realized_pnl),
                status=p.status,
                strategy_id=p.strategy_id,
                opened_at=p.opened_at,
                closed_at=p.closed_at,
            )
            for p in items
        ],
        total=total,
        page=page,
        size=size,
        pages=max(1, (total + size - 1) // size),
    )
