"""IPC client — connects to engine via Unix Domain Socket.

Receives JSON-line events from engine and relays them to WebSocket channels.
Falls back to polling bot_commands table when UDS is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging

from api.ws import channels

logger = logging.getLogger(__name__)

UDS_PATH = "/tmp/traderj.sock"

# Event type → channel broadcast function mapping
_EVENT_HANDLERS: dict[str, object] = {}


def _register_handlers() -> None:
    """Lazy-register event type → broadcast mappings."""
    if _EVENT_HANDLERS:
        return
    _EVENT_HANDLERS.update({
        "MarketTickEvent": _handle_ticker,
        "BotStateChangeEvent": _handle_bot_status,
        "OrderFilledEvent": _handle_order,
        "PositionOpenedEvent": _handle_position,
        "PositionClosedEvent": _handle_position,
        "SignalEvent": _handle_signal,
        "RiskAlertEvent": _handle_alert,
    })


async def _handle_ticker(data: dict) -> None:
    await channels.broadcast_ticker(
        symbol=data.get("symbol", ""),
        price=float(data.get("price", 0)),
        bid=float(data.get("bid", 0)),
        ask=float(data.get("ask", 0)),
        volume_24h=float(data.get("volume_24h", 0)),
        change_pct_24h=float(data.get("change_pct_24h", 0)),
    )


async def _handle_bot_status(data: dict) -> None:
    await channels.broadcast_bot_status(
        strategy_id=data.get("strategy_id", ""),
        state=data.get("state", ""),
        trading_mode=data.get("trading_mode", ""),
        pnl_pct=float(data.get("pnl_pct", 0)),
        open_position=bool(data.get("open_position", False)),
    )


async def _handle_order(data: dict) -> None:
    await channels.broadcast_order(
        order_id=data.get("order_id", ""),
        strategy_id=data.get("strategy_id", ""),
        side=data.get("side", ""),
        amount=str(data.get("amount", "0")),
        price=str(data.get("price", "0")),
        status=data.get("status", ""),
    )


async def _handle_position(data: dict) -> None:
    await channels.broadcast_position(
        position_id=data.get("position_id", ""),
        strategy_id=data.get("strategy_id", ""),
        status=data.get("status", ""),
        unrealized_pnl=str(data.get("unrealized_pnl", "0")),
    )


async def _handle_signal(data: dict) -> None:
    await channels.broadcast_signal(
        strategy_id=data.get("strategy_id", ""),
        direction=data.get("direction", ""),
        score=float(data.get("score", 0)),
        components=data.get("components", {}),
    )


async def _handle_alert(data: dict) -> None:
    await channels.broadcast_alert(
        strategy_id=data.get("strategy_id", ""),
        alert_type=data.get("alert_type", ""),
        message=data.get("message", ""),
        severity=data.get("severity", "info"),
    )


class IPCClient:
    """Reads JSON-line events from engine UDS and relays to WS channels."""

    def __init__(self, socket_path: str = UDS_PATH) -> None:
        self.socket_path = socket_path
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False
        self._reconnect_delay = 1.0

    async def start(self) -> None:
        _register_handlers()
        self._running = True
        asyncio.create_task(self._connect_loop())

    async def stop(self) -> None:
        self._running = False
        if self._writer:
            self._writer.close()
            self._writer = None

    async def send_command(self, strategy_id: str, action: str) -> None:
        """Send a bot control command to engine via UDS."""
        if self._writer is None:
            raise ConnectionError("Not connected to engine")
        msg = json.dumps({"type": "command", "strategy_id": strategy_id, "action": action})
        self._writer.write((msg + "\n").encode())
        await self._writer.drain()

    async def _connect_loop(self) -> None:
        while self._running:
            try:
                self._reader, self._writer = await asyncio.open_unix_connection(
                    self.socket_path
                )
                logger.info("IPC connected to %s", self.socket_path)
                self._reconnect_delay = 1.0
                await self._read_loop()
            except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
                logger.debug("IPC connect failed (%s), retry in %.1fs", e, self._reconnect_delay)
            except Exception:
                logger.exception("IPC unexpected error")

            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 30.0)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while self._running:
            line = await self._reader.readline()
            if not line:
                break  # EOF → reconnect
            try:
                msg = json.loads(line.decode().strip())
                event_type = msg.get("event_type", "")
                handler = _EVENT_HANDLERS.get(event_type)
                if handler:
                    await handler(msg.get("data", {}))
            except json.JSONDecodeError:
                logger.warning("IPC received invalid JSON")
            except Exception:
                logger.exception("IPC event handling error")
