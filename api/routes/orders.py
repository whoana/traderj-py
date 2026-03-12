"""Order history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import OrderResponse, PaginatedResponse

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=PaginatedResponse[OrderResponse])
async def list_orders(
    strategy_id: str | None = None,
    status: str | None = Query(None, pattern="^(pending|filled|cancelled|failed)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    store=Depends(get_store),
):
    orders = await store.get_orders(strategy_id=strategy_id, status=status)
    total = len(orders)
    start = (page - 1) * size
    items = orders[start : start + size]

    return PaginatedResponse(
        items=[
            OrderResponse(
                id=o.id,
                symbol=o.symbol,
                side=o.side,
                order_type=o.order_type,
                amount=str(o.amount),
                price=str(o.price),
                status=o.status,
                strategy_id=o.strategy_id,
                idempotency_key=o.idempotency_key,
                slippage_pct=str(o.slippage_pct) if o.slippage_pct else None,
                created_at=o.created_at,
                filled_at=o.filled_at,
            )
            for o in items
        ],
        total=total,
        page=page,
        size=size,
        pages=max(1, (total + size - 1) // size),
    )
