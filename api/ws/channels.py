"""Channel broadcast helpers — convert engine events to WS payloads."""

from __future__ import annotations

from api.ws.manager import manager


async def broadcast_ticker(symbol: str, price: float, bid: float, ask: float,
                            volume_24h: float, change_pct_24h: float) -> None:
    await manager.broadcast("ticker", {
        "symbol": symbol,
        "price": price,
        "bid": bid,
        "ask": ask,
        "volume_24h": volume_24h,
        "change_pct_24h": change_pct_24h,
    })


async def broadcast_bot_status(strategy_id: str, state: str, trading_mode: str,
                                pnl_pct: float, open_position: bool) -> None:
    await manager.broadcast("bot_status", {
        "strategy_id": strategy_id,
        "state": state,
        "trading_mode": trading_mode,
        "pnl_pct": pnl_pct,
        "open_position": open_position,
    })


async def broadcast_order(order_id: str, strategy_id: str, side: str,
                          amount: str, price: str, status: str) -> None:
    await manager.broadcast("orders", {
        "order_id": order_id,
        "strategy_id": strategy_id,
        "side": side,
        "amount": amount,
        "price": price,
        "status": status,
    })


async def broadcast_position(position_id: str, strategy_id: str, status: str,
                              unrealized_pnl: str) -> None:
    await manager.broadcast("positions", {
        "position_id": position_id,
        "strategy_id": strategy_id,
        "status": status,
        "unrealized_pnl": unrealized_pnl,
    })


async def broadcast_signal(strategy_id: str, direction: str, score: float,
                           components: dict[str, float]) -> None:
    await manager.broadcast("signals", {
        "strategy_id": strategy_id,
        "direction": direction,
        "score": score,
        "components": components,
    })


async def broadcast_alert(strategy_id: str, alert_type: str, message: str,
                          severity: str) -> None:
    await manager.broadcast("alerts", {
        "strategy_id": strategy_id,
        "alert_type": alert_type,
        "message": message,
        "severity": severity,
    })
