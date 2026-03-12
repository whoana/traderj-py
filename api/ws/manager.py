"""WebSocket connection manager — handles subscriptions and broadcasting."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)

VALID_CHANNELS = {"ticker", "bot_status", "orders", "positions", "signals", "alerts"}
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 60  # close if no pong within this


class ConnectionManager:
    """Manages all active WebSocket connections and their channel subscriptions."""

    def __init__(self) -> None:
        # ws → set of subscribed channels
        self._subscriptions: dict[WebSocket, set[str]] = {}
        # channel → set of subscribed ws
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._last_pong: dict[WebSocket, float] = {}

    @property
    def connection_count(self) -> int:
        return len(self._subscriptions)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._subscriptions[ws] = set()
            self._last_pong[ws] = time.time()
        logger.info("WS connected, total=%d", self.connection_count)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            channels = self._subscriptions.pop(ws, set())
            for ch in channels:
                self._channels[ch].discard(ws)
            self._last_pong.pop(ws, None)
        logger.info("WS disconnected, total=%d", self.connection_count)

    async def subscribe(self, ws: WebSocket, channels: list[str]) -> list[str]:
        valid = [ch for ch in channels if ch in VALID_CHANNELS]
        async with self._lock:
            if ws not in self._subscriptions:
                return []
            self._subscriptions[ws].update(valid)
            for ch in valid:
                self._channels[ch].add(ws)
        return valid

    async def unsubscribe(self, ws: WebSocket, channels: list[str]) -> list[str]:
        removed = []
        async with self._lock:
            if ws not in self._subscriptions:
                return []
            for ch in channels:
                if ch in self._subscriptions[ws]:
                    self._subscriptions[ws].discard(ch)
                    self._channels[ch].discard(ws)
                    removed.append(ch)
        return removed

    async def broadcast(self, channel: str, payload: dict) -> None:
        """Send data message to all subscribers of a channel."""
        message = json.dumps({
            "type": "data",
            "channel": channel,
            "payload": payload,
            "ts": int(time.time() * 1000),
        })
        async with self._lock:
            subscribers = list(self._channels.get(channel, set()))
        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                await self.disconnect(ws)

    async def send_personal(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            await self.disconnect(ws)

    async def handle_message(self, ws: WebSocket, data: str) -> None:
        """Process an incoming client message."""
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            await self.send_personal(ws, {
                "type": "error", "code": "invalid_json", "message": "Invalid JSON"
            })
            return

        msg_type = msg.get("type")

        if msg_type == "subscribe":
            channels = msg.get("channels", [])
            subscribed = await self.subscribe(ws, channels)
            await self.send_personal(ws, {"type": "subscribed", "channels": subscribed})

        elif msg_type == "unsubscribe":
            channels = msg.get("channels", [])
            removed = await self.unsubscribe(ws, channels)
            await self.send_personal(ws, {"type": "unsubscribed", "channels": removed})

        elif msg_type == "pong":
            async with self._lock:
                self._last_pong[ws] = time.time()

        else:
            await self.send_personal(ws, {
                "type": "error",
                "code": "unknown_type",
                "message": f"Unknown message type: {msg_type}",
            })

    async def heartbeat_loop(self) -> None:
        """Send pings and clean up stale connections."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            now = time.time()
            async with self._lock:
                all_ws = list(self._subscriptions.keys())
                stale = [
                    ws for ws in all_ws
                    if now - self._last_pong.get(ws, now) > HEARTBEAT_TIMEOUT
                ]

            # Disconnect stale
            for ws in stale:
                logger.warning("WS heartbeat timeout, disconnecting")
                await self.disconnect(ws)
                try:
                    await ws.close(code=1001, reason="Heartbeat timeout")
                except Exception:
                    pass

            # Ping remaining
            ping_msg = json.dumps({"type": "ping"})
            async with self._lock:
                remaining = list(self._subscriptions.keys())
            for ws in remaining:
                try:
                    await ws.send_text(ping_msg)
                except Exception:
                    await self.disconnect(ws)


# Singleton manager
manager = ConnectionManager()
