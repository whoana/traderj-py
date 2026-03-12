"""Unit tests for bootstrap wiring."""

from __future__ import annotations

import pytest

from engine.bootstrap import bootstrap
from engine.config.settings import AppSettings
from engine.data.sqlite_store import SqliteDataStore
from engine.execution.order_manager import OrderManager
from engine.execution.position_manager import PositionManager
from engine.execution.risk_manager import RiskManager
from engine.loop.ipc_server import IPCServer
from engine.loop.state import StateMachine
from engine.loop.trading_loop import TradingLoop
from engine.strategy.signal import SignalGenerator


@pytest.fixture
async def store():
    s = SqliteDataStore(":memory:")
    await s.connect()
    yield s
    await s.disconnect()


async def test_bootstrap_registers_all_components(store):
    """bootstrap() should register all required components."""
    settings = AppSettings()
    app = await bootstrap(settings=settings, data_store=store)

    # Verify all core components are registered
    assert app.get("datastore") is store
    assert isinstance(app.get("signal_generator"), SignalGenerator)
    assert isinstance(app.get("order_manager"), OrderManager)
    assert isinstance(app.get("position_manager"), PositionManager)
    assert isinstance(app.get("risk_manager"), RiskManager)
    assert isinstance(app.get("state_machine"), StateMachine)
    assert isinstance(app.get("trading_loop"), TradingLoop)
    assert isinstance(app.get("ipc_server"), IPCServer)

    # exchange is also registered
    assert app.get("exchange") is not None


async def test_bootstrap_uses_correct_strategy(store):
    """bootstrap() should load the correct strategy preset."""
    settings = AppSettings()
    settings.trading.strategy_id = "STR-002"

    app = await bootstrap(settings=settings, data_store=store)
    signal_gen = app.get("signal_generator")

    assert signal_gen.strategy_id == "STR-002"
    assert signal_gen.buy_threshold == 0.05  # STR-002 threshold (tuned)


async def test_bootstrap_fallback_to_default_strategy(store):
    """bootstrap() should fallback to default if strategy not found."""
    settings = AppSettings()
    settings.trading.strategy_id = "NONEXISTENT"

    app = await bootstrap(settings=settings, data_store=store)
    signal_gen = app.get("signal_generator")

    # Falls back to default preset's thresholds (tuned)
    assert signal_gen.buy_threshold == 0.08


async def test_bootstrap_event_subscriptions(store):
    """bootstrap() should wire event bus subscriptions."""
    settings = AppSettings()
    app = await bootstrap(settings=settings, data_store=store)

    # EventBus should have handlers registered
    assert app.event_bus.handler_count >= 4


async def test_bootstrap_ipc_has_command_handler(store):
    """bootstrap() should set command handler on IPCServer."""
    settings = AppSettings()
    app = await bootstrap(settings=settings, data_store=store)

    ipc = app.get("ipc_server")
    assert ipc._command_handler is not None


async def test_bootstrap_trading_mode(store):
    """bootstrap() should correctly set trading mode."""
    settings = AppSettings()
    settings.trading.mode = "paper"

    app = await bootstrap(settings=settings, data_store=store)
    state_machine = app.get("state_machine")

    assert state_machine._trading_mode == "paper"
