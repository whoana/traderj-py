"""Upbit WebSocket Stream — real-time market data feed.

Implements the shared WebSocketStream Protocol.
Connects to Upbit WebSocket API for ticker and trade data.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import websockets

logger = logging.getLogger(__name__)

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


class UpbitWebSocketStream:
    """Async Upbit WebSocket client for real-time market data."""

    def __init__(self, reconnect_delay: float = 5.0, max_reconnects: int = 10) -> None:
        self._ws: Any = None
        self._reconnect_delay = reconnect_delay
        self._max_reconnects = max_reconnects
        self._channels: list[str] = []
        self._handlers: list[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Upbit WebSocket stream started")

    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Upbit WebSocket stream stopped")

    async def subscribe(self, channels: list[str]) -> None:
        """Subscribe to channels.

        Channels format: ["ticker.KRW-BTC", "trade.KRW-BTC"]
        """
        self._channels = channels
        if self._ws:
            await self._send_subscription()

    async def on_message(self, handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        self._handlers.append(handler)

    async def _run_loop(self) -> None:
        reconnect_count = 0
        while self._running and reconnect_count < self._max_reconnects:
            try:
                async with websockets.connect(UPBIT_WS_URL, ping_interval=30) as ws:
                    self._ws = ws
                    reconnect_count = 0
                    logger.info("WebSocket connected to %s", UPBIT_WS_URL)

                    if self._channels:
                        await self._send_subscription()

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            if isinstance(raw_msg, bytes):
                                data = json.loads(raw_msg.decode("utf-8"))
                            else:
                                data = json.loads(raw_msg)
                            for handler in self._handlers:
                                await handler(data)
                        except json.JSONDecodeError:
                            logger.warning("Invalid WebSocket message: %s", raw_msg[:100])
                        except Exception:
                            logger.exception("Error handling WebSocket message")

            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
            except Exception:
                logger.exception("WebSocket error, reconnecting...")

            if self._running:
                reconnect_count += 1
                await asyncio.sleep(self._reconnect_delay)

        if reconnect_count >= self._max_reconnects:
            logger.error("Max WebSocket reconnects (%d) reached", self._max_reconnects)

    async def _send_subscription(self) -> None:
        if not self._ws or not self._channels:
            return

        # Build Upbit subscription message
        # Format: [{"ticket":"uuid"},{"type":"ticker","codes":["KRW-BTC"]}, ...]
        ticket = {"ticket": str(uuid.uuid4())}
        subs: list[dict[str, Any]] = []

        ticker_codes: list[str] = []
        trade_codes: list[str] = []

        for ch in self._channels:
            parts = ch.split(".", 1)
            ch_type = parts[0]
            code = parts[1] if len(parts) > 1 else ""
            if ch_type == "ticker" and code:
                ticker_codes.append(code)
            elif ch_type == "trade" and code:
                trade_codes.append(code)

        if ticker_codes:
            subs.append({"type": "ticker", "codes": ticker_codes})
        if trade_codes:
            subs.append({"type": "trade", "codes": trade_codes})

        if subs:
            msg = json.dumps([ticket] + subs)
            await self._ws.send(msg)
            logger.info("Subscribed to channels: %s", self._channels)
