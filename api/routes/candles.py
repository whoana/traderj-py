"""OHLCV candle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import CandleResponse

router = APIRouter(prefix="/candles", tags=["candles"], dependencies=[Depends(verify_api_key)])


@router.get("/{symbol}/{timeframe}", response_model=list[CandleResponse])
async def get_candles(
    symbol: str,
    timeframe: str,
    limit: int = Query(200, ge=1, le=1000),
    store=Depends(get_store),
):
    # URL path uses dash-separated symbol (BTC-KRW → BTC/KRW)
    sym = symbol.replace("-", "/")
    candles = await store.get_candles(symbol=sym, timeframe=timeframe, limit=limit)

    return [
        CandleResponse(
            time=c.time,
            open=float(c.open),
            high=float(c.high),
            low=float(c.low),
            close=float(c.close),
            volume=float(c.volume),
        )
        for c in candles
    ]
