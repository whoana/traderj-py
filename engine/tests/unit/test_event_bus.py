"""Unit tests for EventBus."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from engine.loop.event_bus import EventBus
from shared.events import (
    MarketTickEvent,
    SignalEvent,
    BotStateChangeEvent,
)
from shared.enums import BotStateEnum, SignalDirection


class TestEventBus:
    async def test_subscribe_and_publish(self) -> None:
        bus = EventBus()
        received: list[MarketTickEvent] = []

        async def handler(event: MarketTickEvent) -> None:
            received.append(event)

        bus.subscribe(MarketTickEvent, handler)
        await bus.start()

        event = MarketTickEvent(
            symbol="BTC/KRW",
            price=Decimal("50000000"),
            bid=Decimal("49999000"),
            ask=Decimal("50001000"),
            volume_24h=Decimal("1000"),
        )
        await bus.publish(event)
        await asyncio.sleep(0.05)
        await bus.stop()

        assert len(received) == 1
        assert received[0].symbol == "BTC/KRW"

    async def test_multiple_handlers(self) -> None:
        bus = EventBus()
        results_a: list[SignalEvent] = []
        results_b: list[SignalEvent] = []

        async def handler_a(event: SignalEvent) -> None:
            results_a.append(event)

        async def handler_b(event: SignalEvent) -> None:
            results_b.append(event)

        bus.subscribe(SignalEvent, handler_a)
        bus.subscribe(SignalEvent, handler_b)
        await bus.start()

        event = SignalEvent(
            strategy_id="STR-001",
            symbol="BTC/KRW",
            direction=SignalDirection.BUY,
            score=0.8,
            components={"trend": 0.9},
            details={},
        )
        await bus.publish(event)
        await asyncio.sleep(0.05)
        await bus.stop()

        assert len(results_a) == 1
        assert len(results_b) == 1

    async def test_handler_error_isolation(self) -> None:
        """A failing handler should not prevent other handlers from running."""
        bus = EventBus()
        received: list[MarketTickEvent] = []

        async def bad_handler(event: MarketTickEvent) -> None:
            raise ValueError("Intentional error")

        async def good_handler(event: MarketTickEvent) -> None:
            received.append(event)

        bus.subscribe(MarketTickEvent, bad_handler)
        bus.subscribe(MarketTickEvent, good_handler)
        await bus.start()

        event = MarketTickEvent(
            symbol="BTC/KRW",
            price=Decimal("50000000"),
            bid=Decimal("49999000"),
            ask=Decimal("50001000"),
            volume_24h=Decimal("1000"),
        )
        await bus.publish(event)
        await asyncio.sleep(0.05)
        await bus.stop()

        # Good handler should still receive the event
        assert len(received) == 1

    async def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[MarketTickEvent] = []

        async def handler(event: MarketTickEvent) -> None:
            received.append(event)

        bus.subscribe(MarketTickEvent, handler)
        bus.unsubscribe(MarketTickEvent, handler)
        await bus.start()

        event = MarketTickEvent(
            symbol="BTC/KRW",
            price=Decimal("50000000"),
            bid=Decimal("49999000"),
            ask=Decimal("50001000"),
            volume_24h=Decimal("1000"),
        )
        await bus.publish(event)
        await asyncio.sleep(0.05)
        await bus.stop()

        assert len(received) == 0

    async def test_type_isolation(self) -> None:
        """Events only go to handlers subscribed to that type."""
        bus = EventBus()
        tick_received: list[MarketTickEvent] = []
        signal_received: list[SignalEvent] = []

        async def tick_handler(event: MarketTickEvent) -> None:
            tick_received.append(event)

        async def signal_handler(event: SignalEvent) -> None:
            signal_received.append(event)

        bus.subscribe(MarketTickEvent, tick_handler)
        bus.subscribe(SignalEvent, signal_handler)
        await bus.start()

        await bus.publish(
            MarketTickEvent(
                symbol="BTC/KRW",
                price=Decimal("50000000"),
                bid=Decimal("49999000"),
                ask=Decimal("50001000"),
                volume_24h=Decimal("1000"),
            )
        )
        await asyncio.sleep(0.05)
        await bus.stop()

        assert len(tick_received) == 1
        assert len(signal_received) == 0

    async def test_handler_count(self) -> None:
        bus = EventBus()

        async def h1(event: MarketTickEvent) -> None:
            pass

        async def h2(event: SignalEvent) -> None:
            pass

        assert bus.handler_count == 0
        bus.subscribe(MarketTickEvent, h1)
        assert bus.handler_count == 1
        bus.subscribe(SignalEvent, h2)
        assert bus.handler_count == 2

    async def test_publish_nowait(self) -> None:
        bus = EventBus()
        received: list[MarketTickEvent] = []

        async def handler(event: MarketTickEvent) -> None:
            received.append(event)

        bus.subscribe(MarketTickEvent, handler)
        await bus.start()

        event = MarketTickEvent(
            symbol="BTC/KRW",
            price=Decimal("50000000"),
            bid=Decimal("49999000"),
            ask=Decimal("50001000"),
            volume_24h=Decimal("1000"),
        )
        bus.publish_nowait(event)
        await asyncio.sleep(0.05)
        await bus.stop()

        assert len(received) == 1

    async def test_start_stop_idempotent(self) -> None:
        bus = EventBus()
        await bus.start()
        await bus.start()  # Should not raise
        assert bus.is_running
        await bus.stop()
        await bus.stop()  # Should not raise
        assert not bus.is_running
