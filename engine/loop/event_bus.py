"""asyncio EventBus for decoupled pub/sub communication.

Supports 13 event types. Handler errors are isolated so a single
handler failure does not affect other handlers.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    """asyncio-based event bus with type-based pub/sub."""

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: EventHandler) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Any) -> None:
        """Publish an event to the bus.

        Events are queued and processed asynchronously.
        """
        await self._queue.put(event)

    def publish_nowait(self, event: Any) -> None:
        """Non-blocking publish. Use when not in async context."""
        self._queue.put_nowait(event)

    async def start(self) -> None:
        """Start the event processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("EventBus started")

    async def stop(self) -> None:
        """Stop the event processing loop.

        Drains remaining events before stopping.
        """
        if not self._running:
            return
        self._running = False
        # Signal the loop to exit
        await self._queue.put(None)
        if self._task:
            await self._task
            self._task = None
        logger.info("EventBus stopped")

    async def _process_loop(self) -> None:
        """Main processing loop — dequeue events and dispatch to handlers."""
        while self._running:
            event = await self._queue.get()
            if event is None:
                break
            await self._dispatch(event)
            self._queue.task_done()

        # Drain remaining events
        while not self._queue.empty():
            event = self._queue.get_nowait()
            if event is not None:
                await self._dispatch(event)
            self._queue.task_done()

    async def _dispatch(self, event: Any) -> None:
        """Dispatch event to all registered handlers.

        Handler errors are isolated — a failing handler does not
        affect other handlers for the same event.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Handler %s failed for event %s",
                    handler.__qualname__,
                    event_type.__name__,
                )

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers across all event types."""
        return sum(len(h) for h in self._handlers.values())

    @property
    def is_running(self) -> bool:
        return self._running
