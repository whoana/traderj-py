"""Risk state endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_store
from api.middleware.auth import verify_api_key
from api.schemas.responses import RiskStateResponse

router = APIRouter(prefix="/risk", tags=["risk"], dependencies=[Depends(verify_api_key)])


@router.get("/{strategy_id}", response_model=RiskStateResponse)
async def get_risk_state(strategy_id: str, store=Depends(get_store)):
    risk = await store.get_risk_state(strategy_id)
    if risk is None:
        raise HTTPException(status_code=404, detail=f"Risk state for {strategy_id} not found")
    return RiskStateResponse(
        strategy_id=risk.strategy_id,
        consecutive_losses=risk.consecutive_losses,
        daily_pnl=str(risk.daily_pnl),
        cooldown_until=risk.cooldown_until,
        last_updated=risk.last_updated,
    )
