"""Signal history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import PaginatedResponse, SignalResponse

router = APIRouter(prefix="/signals", tags=["signals"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=PaginatedResponse[SignalResponse])
async def list_signals(
    strategy_id: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    store=Depends(get_store),
):
    signals = await store.get_signals(strategy_id=strategy_id, limit=size * page)
    total = len(signals)
    start = (page - 1) * size
    items = signals[start : start + size]

    return PaginatedResponse(
        items=[
            SignalResponse(
                id=s.id,
                symbol=s.symbol,
                strategy_id=s.strategy_id,
                direction=s.direction,
                score=float(s.score),
                components=s.components,
                details=s.details,
                created_at=s.created_at,
            )
            for s in items
        ],
        total=total,
        page=page,
        size=size,
        pages=max(1, (total + size - 1) // size),
    )
