"""Paper balance endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_exchange, get_store
from api.middleware.auth import verify_api_key

router = APIRouter(prefix="/balance", tags=["balance"], dependencies=[Depends(verify_api_key)])


@router.get("")
async def get_balance(
    strategy_id: str = Query("STR-001"),
    store=Depends(get_store),
    exchange=Depends(get_exchange),
):
    balance = await store.get_paper_balance(strategy_id)
    if balance is None:
        return {
            "strategy_id": strategy_id,
            "krw": "0",
            "btc": "0",
            "initial_krw": "0",
            "total_value_krw": "0",
            "pnl_krw": "0",
            "pnl_pct": 0.0,
        }

    krw = float(balance.krw)
    btc = float(balance.btc)
    initial = float(balance.initial_krw)

    # Get current BTC price for total value
    btc_value = 0.0
    if btc > 0 and exchange is not None:
        try:
            ticker = await exchange.fetch_ticker("BTC/KRW")
            btc_value = btc * float(ticker.get("last", 0))
        except Exception:
            pass

    total = krw + btc_value
    pnl = total - initial
    pnl_pct = (pnl / initial * 100) if initial > 0 else 0.0

    return {
        "strategy_id": strategy_id,
        "krw": str(balance.krw),
        "btc": str(balance.btc),
        "initial_krw": str(balance.initial_krw),
        "total_value_krw": f"{total:.0f}",
        "pnl_krw": f"{pnl:.0f}",
        "pnl_pct": round(pnl_pct, 2),
    }
