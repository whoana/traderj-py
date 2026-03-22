"""IPC server — engine-side Unix Domain Socket server.

Streams events to API process and receives bot control commands.
Commands are saved to DB and optionally dispatched immediately
via a registered command handler callback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable, Coroutine
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)

UDS_PATH = "/tmp/traderj.sock"

CommandHandler = Callable[[str, str, dict[str, Any]], Coroutine[Any, Any, None]]


class IPCServer:
    """UDS server that streams engine events to API clients."""

    def __init__(self, event_bus, data_store, socket_path: str = UDS_PATH) -> None:
        self.event_bus = event_bus
        self.data_store = data_store
        self.socket_path = socket_path
        self._server: asyncio.AbstractServer | None = None
        self._clients: list[asyncio.StreamWriter] = []
        self._lock = asyncio.Lock()
        self._command_handler: CommandHandler | None = None

    def set_command_handler(self, handler: CommandHandler) -> None:
        """Register a callback for immediate command dispatch.

        The handler receives (command, strategy_id, params) and is called
        after saving to DB, enabling immediate execution without polling.
        """
        self._command_handler = handler

    async def start(self) -> None:
        # Clean up stale socket file
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self.socket_path
        )
        logger.info("IPC server listening on %s", self.socket_path)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        async with self._lock:
            for writer in self._clients:
                writer.close()
            self._clients.clear()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        logger.info("IPC server stopped")

    async def broadcast_event(self, event_type: str, data: dict) -> None:
        """Send an event to all connected API clients."""
        msg = json.dumps({"event_type": event_type, "data": data}) + "\n"
        encoded = msg.encode()
        async with self._lock:
            dead = []
            for writer in self._clients:
                try:
                    writer.write(encoded)
                    await writer.drain()
                except Exception:
                    dead.append(writer)
            for w in dead:
                self._clients.remove(w)

    async def _handle_client(self, reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter) -> None:
        async with self._lock:
            self._clients.append(writer)
        logger.info("IPC client connected, total=%d", len(self._clients))

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode().strip())
                    if msg.get("type") == "command":
                        await self._handle_command(msg)
                except json.JSONDecodeError:
                    pass
                except Exception:
                    logger.exception("IPC command handling error")
        finally:
            async with self._lock:
                if writer in self._clients:
                    self._clients.remove(writer)
            writer.close()
            logger.info("IPC client disconnected, total=%d", len(self._clients))

    async def _handle_command(self, msg: dict) -> None:
        """Process a bot control command from API."""
        import uuid
        from datetime import datetime

        from shared.models import BotCommand

        cmd = BotCommand(
            id=str(uuid.uuid4()),
            command=msg.get("action", ""),
            strategy_id=msg.get("strategy_id", ""),
            params=msg.get("params", {}),
            status="pending",
            created_at=datetime.now(UTC),
        )
        await self.data_store.save_bot_command(cmd)
        logger.info("IPC command queued: %s %s", cmd.command, cmd.strategy_id)

        # Dispatch immediately if handler registered
        if self._command_handler is not None:
            try:
                await self._command_handler(cmd.command, cmd.strategy_id, cmd.params)
                await self.data_store.mark_command_processed(cmd.id)
                logger.info("IPC command executed immediately: %s %s", cmd.command, cmd.strategy_id)
            except Exception:
                logger.exception("Immediate command dispatch failed: %s", cmd.command)
