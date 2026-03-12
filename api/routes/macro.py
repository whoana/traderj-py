"""Macro snapshot endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import MacroSnapshotResponse

router = APIRouter(prefix="/macro", tags=["macro"], dependencies=[Depends(verify_api_key)])


@router.get("/latest", response_model=MacroSnapshotResponse)
async def get_latest_macro(store=Depends(get_store)):
    snapshot = await store.get_latest_macro()
    if snapshot is None:
        # Return default values when no macro data collected yet
        from datetime import datetime, timezone

        return MacroSnapshotResponse(
            timestamp=datetime.now(timezone.utc),
            fear_greed=50.0,
            funding_rate=0.0,
            btc_dominance=50.0,
            btc_dom_7d_change=0.0,
            dxy=100.0,
            kimchi_premium=0.0,
            market_score=0.5,
        )
    return MacroSnapshotResponse(
        timestamp=snapshot.timestamp,
        fear_greed=float(snapshot.fear_greed),
        funding_rate=float(snapshot.funding_rate),
        btc_dominance=float(snapshot.btc_dominance),
        btc_dom_7d_change=float(snapshot.btc_dom_7d_change),
        dxy=float(snapshot.dxy),
        kimchi_premium=float(snapshot.kimchi_premium),
        market_score=float(snapshot.market_score),
    )
