"""Unit tests for multi-strategy concurrent execution.

Tests:
- Multiple strategies bootstrap correctly
- Each strategy has independent components
- IPC command routing dispatches to correct strategy
- Emergency exit broadcasts to all strategies
- Shared components are truly shared
- Each strategy runs independent ticks
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
import pytest

from engine.bootstrap import bootstrap
from engine.config.settings import AppSettings
from engine.data.sqlite_store import SqliteDataStore
from engine.loop.trading_loop import TradingLoop
from engine.strategy.signal import SignalGenerator
from shared.enums import BotStateEnum, SignalDirection, TradingMode
from shared.models import Candle, PaperBalance


# ── Fixtures ─────────────────────────────────────────────────────


class FakeExchange:
    """Minimal exchange mock for multi-strategy tests."""

    def __init__(self, price: float = 90_000_000.0):
        self.price = price

    async def fetch_ticker(self, symbol: str) -> dict:
        return {
            "last": str(self.price),
            "bid": str(self.price - 10000),
            "ask": str(self.price + 10000),
            "volume": "100",
        }

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        candles = []
        base = self.price
        for i in range(limit):
            t = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
            variation = 1 + (i % 7 - 3) * 0.005
            close_price = base * variation
            candles.append(Candle(
                time=t,
                symbol=symbol,
                timeframe=timeframe,
                open=Decimal(str(base)),
                high=Decimal(str(max(base, close_price) * 1.005)),
                low=Decimal(str(min(base, close_price) * 0.995)),
                close=Decimal(str(close_price)),
                volume=Decimal(str(10 + i % 5)),
            ))
        return candles


@pytest.fixture
async def store():
    s = SqliteDataStore(":memory:")
    await s.connect()
    yield s
    await s.disconnect()


# ── Multi-strategy bootstrap tests ──────────────────────────────


class TestMultiStrategyBootstrap:
    async def test_two_strategies_registered(self, store):
        """Bootstrap with 2 strategies should register per-strategy components."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)

        # Shared components
        assert app.get("datastore") is store
        assert app.get("exchange") is not None

        # Per-strategy components (with :strategy_id suffix)
        assert isinstance(app.get("trading_loop:STR-001"), TradingLoop)
        assert isinstance(app.get("trading_loop:STR-002"), TradingLoop)
        assert isinstance(app.get("signal_generator:STR-001"), SignalGenerator)
        assert isinstance(app.get("signal_generator:STR-002"), SignalGenerator)

    async def test_trading_loops_map(self, store):
        """trading_loops dict should contain all strategies."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002", "STR-003"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        assert len(trading_loops) == 3
        assert "STR-001" in trading_loops
        assert "STR-002" in trading_loops
        assert "STR-003" in trading_loops

    async def test_each_strategy_has_correct_preset(self, store):
        """Each strategy's SignalGenerator should use its own preset."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)

        sg1 = app.get("signal_generator:STR-001")
        sg2 = app.get("signal_generator:STR-002")

        # STR-001 is conservative (threshold=0.10, tuned)
        assert sg1.strategy_id == "STR-001"
        assert sg1.buy_threshold == 0.10

        # STR-002 is aggressive (threshold=0.05, tuned)
        assert sg2.strategy_id == "STR-002"
        assert sg2.buy_threshold == 0.05

    async def test_shared_datastore(self, store):
        """All strategies should share the same DataStore instance."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        loop1 = trading_loops["STR-001"]
        loop2 = trading_loops["STR-002"]

        assert loop1._store is loop2._store

    async def test_shared_event_bus(self, store):
        """All strategies should share the same EventBus."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        loop1 = trading_loops["STR-001"]
        loop2 = trading_loops["STR-002"]

        assert loop1._bus is loop2._bus
        assert loop1._bus is app.event_bus

    async def test_shared_exchange(self, store):
        """All strategies should share the same exchange client."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        assert trading_loops["STR-001"]._exchange is trading_loops["STR-002"]._exchange

    async def test_independent_state_machines(self, store):
        """Each strategy should have its own StateMachine."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)

        sm1 = app.get("state_machine:STR-001")
        sm2 = app.get("state_machine:STR-002")

        assert sm1 is not sm2
        assert sm1._strategy_id == "STR-001"
        assert sm2._strategy_id == "STR-002"

    async def test_event_subscriptions_wired_per_strategy(self, store):
        """Each strategy should have its own event subscriptions."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)

        # 4 subscriptions per strategy × 2 strategies = 8
        assert app.event_bus.handler_count >= 8


class TestMultiStrategySettings:
    def test_get_active_strategy_ids_from_list(self):
        """strategy_ids list should take precedence."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]
        settings.trading.strategy_id = "STR-003"

        assert settings.trading.get_active_strategy_ids() == ["STR-001", "STR-002"]

    def test_get_active_strategy_ids_fallback(self):
        """Empty strategy_ids should fall back to strategy_id."""
        settings = AppSettings()
        settings.trading.strategy_ids = []
        settings.trading.strategy_id = "STR-003"

        assert settings.trading.get_active_strategy_ids() == ["STR-003"]


class TestSingleStrategyBackwardCompat:
    async def test_single_strategy_no_suffix(self, store):
        """Single strategy should use plain component names (no suffix)."""
        settings = AppSettings()
        settings.trading.strategy_id = "STR-001"
        settings.trading.strategy_ids = []

        app = await bootstrap(settings=settings, data_store=store)

        # Should use plain names (backward compat)
        assert isinstance(app.get("trading_loop"), TradingLoop)
        assert isinstance(app.get("signal_generator"), SignalGenerator)

        # trading_loops dict still works
        trading_loops = app.get("trading_loops")
        assert len(trading_loops) == 1
        assert "STR-001" in trading_loops


# ── Multi-strategy command routing tests ─────────────────────────


class TestCommandRouting:
    async def test_command_routed_to_correct_strategy(self, store):
        """IPC commands should be routed to the correct strategy's TradingLoop."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        loop1 = trading_loops["STR-001"]
        loop2 = trading_loops["STR-002"]

        # Start both loops
        await loop1.start()
        await loop2.start()

        assert loop1._state.state == BotStateEnum.SCANNING
        assert loop2._state.state == BotStateEnum.SCANNING

        # Get the command handler from IPC
        ipc = app.get("ipc_server")
        handler = ipc._command_handler
        assert handler is not None

        # Pause only STR-001
        await handler("pause", "STR-001", {})

        assert loop1._state.state == BotStateEnum.PAUSED
        assert loop2._state.state == BotStateEnum.SCANNING

        # Clean up
        await loop1.stop()
        await loop2.stop()

    async def test_command_broadcast_on_empty_strategy_id(self, store):
        """Empty strategy_id should broadcast to all strategies."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        for loop in trading_loops.values():
            await loop.start()

        ipc = app.get("ipc_server")
        handler = ipc._command_handler

        # Broadcast pause to all
        await handler("pause", "", {})

        for loop in trading_loops.values():
            assert loop._state.state == BotStateEnum.PAUSED

        for loop in trading_loops.values():
            await loop.stop()

    async def test_command_unknown_strategy_ignored(self, store):
        """Command for unknown strategy should be ignored without error."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001"]

        app = await bootstrap(settings=settings, data_store=store)
        ipc = app.get("ipc_server")
        handler = ipc._command_handler

        # Should not raise
        await handler("pause", "NONEXISTENT", {})


# ── Multi-strategy concurrent execution tests ────────────────────


class TestConcurrentExecution:
    async def test_independent_paper_balances(self, store):
        """Each strategy should have its own paper balance."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        # Start both to initialize paper balances
        for loop in trading_loops.values():
            await loop.start()

        bal1 = await store.get_paper_balance("STR-001")
        bal2 = await store.get_paper_balance("STR-002")

        assert bal1 is not None
        assert bal2 is not None
        assert bal1.strategy_id == "STR-001"
        assert bal2.strategy_id == "STR-002"

        for loop in trading_loops.values():
            await loop.stop()

    async def test_independent_start_stop(self, store):
        """Starting/stopping one strategy should not affect others."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        loop1 = trading_loops["STR-001"]
        loop2 = trading_loops["STR-002"]

        await loop1.start()
        await loop2.start()

        # Stop only STR-001
        await loop1.stop()

        assert not loop1.is_running
        assert loop2.is_running
        assert loop1._state.state == BotStateEnum.IDLE
        assert loop2._state.state == BotStateEnum.SCANNING

        await loop2.stop()

    async def test_independent_pause_resume(self, store):
        """Pausing one strategy should not affect others."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        for loop in trading_loops.values():
            await loop.start()

        # Pause STR-001
        await trading_loops["STR-001"].pause()

        assert trading_loops["STR-001"]._state.state == BotStateEnum.PAUSED
        assert trading_loops["STR-002"]._state.state == BotStateEnum.SCANNING

        # Resume STR-001
        await trading_loops["STR-001"].resume()
        assert trading_loops["STR-001"]._state.state == BotStateEnum.SCANNING

        for loop in trading_loops.values():
            await loop.stop()

    async def test_concurrent_ticks(self, store):
        """Multiple strategies should tick independently."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        # Replace exchange with fake
        fake_exchange = FakeExchange()
        for loop in trading_loops.values():
            loop._exchange = fake_exchange

        for loop in trading_loops.values():
            await loop.start()

        # Run ticks concurrently
        results = await asyncio.gather(
            trading_loops["STR-001"].tick(),
            trading_loops["STR-002"].tick(),
        )

        # Both should produce signals
        assert results[0] is not None
        assert results[1] is not None
        assert results[0].direction in (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD)
        assert results[1].direction in (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD)

        # Each should have incremented tick count
        assert trading_loops["STR-001"].tick_count == 1
        assert trading_loops["STR-002"].tick_count == 1

        for loop in trading_loops.values():
            await loop.stop()

    async def test_signals_saved_with_correct_strategy_id(self, store):
        """Each strategy's signals should be saved with correct strategy_id."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        fake_exchange = FakeExchange()
        for loop in trading_loops.values():
            loop._exchange = fake_exchange
            await loop.start()

        # Tick both
        await trading_loops["STR-001"].tick()
        await trading_loops["STR-002"].tick()

        # Check signals in DB
        signals_1 = await store.get_signals(strategy_id="STR-001")
        signals_2 = await store.get_signals(strategy_id="STR-002")

        assert len(signals_1) >= 1
        assert len(signals_2) >= 1
        assert all(s.strategy_id == "STR-001" for s in signals_1)
        assert all(s.strategy_id == "STR-002" for s in signals_2)

        for loop in trading_loops.values():
            await loop.stop()

    async def test_three_strategies_concurrent(self, store):
        """Three strategies running concurrently."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002", "STR-003"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        assert len(trading_loops) == 3

        fake_exchange = FakeExchange()
        for loop in trading_loops.values():
            loop._exchange = fake_exchange
            await loop.start()

        # Tick all concurrently
        results = await asyncio.gather(*[loop.tick() for loop in trading_loops.values()])

        assert all(r is not None for r in results)
        assert all(loop.tick_count == 1 for loop in trading_loops.values())

        for loop in trading_loops.values():
            await loop.stop()


class TestMultiStrategyEmergencyExit:
    async def test_emergency_broadcast(self, store):
        """Emergency exit broadcast should stop all strategies."""
        settings = AppSettings()
        settings.trading.strategy_ids = ["STR-001", "STR-002"]

        app = await bootstrap(settings=settings, data_store=store)
        trading_loops = app.get("trading_loops")

        for loop in trading_loops.values():
            await loop.start()
            assert loop.is_running

        ipc = app.get("ipc_server")
        handler = ipc._command_handler

        # Broadcast emergency_exit
        await handler("emergency_exit", "", {})

        for loop in trading_loops.values():
            assert not loop.is_running
            assert loop._state.state == BotStateEnum.IDLE
