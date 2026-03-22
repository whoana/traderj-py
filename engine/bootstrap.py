"""Bootstrap — wire all engine components into AppOrchestrator.

Supports single-strategy and multi-strategy modes:
  - Single: TRADING_STRATEGY_ID=STR-001 (backward compatible)
  - Multi:  TRADING_STRATEGY_IDS='["STR-001","STR-002"]'

Shared components (one instance):
  DataStore, EventBus, Exchange, Scheduler, IPCServer

Per-strategy components (one per strategy_id):
  SignalGenerator, CircuitBreaker, OrderManager, PositionManager,
  RiskManager, StateMachine, TradingLoop
"""

from __future__ import annotations

import logging
from typing import Any

from engine.app import AppOrchestrator
from engine.config.settings import AppSettings
from engine.execution.circuit_breaker import CircuitBreaker
from engine.execution.order_manager import OrderManager
from engine.execution.position_manager import PositionManager
from engine.execution.risk_manager import RiskManager
from engine.exchange.upbit_client import UpbitExchangeClient
from engine.data.macro import MacroCollector
from engine.loop.ipc_server import IPCServer
from engine.loop.state import StateMachine
from engine.loop.trading_loop import TradingLoop
from engine.strategy.presets import STRATEGY_PRESETS
from engine.strategy.regime_switch import RegimeSwitchManager
from engine.strategy.signal import SignalGenerator
from shared.enums import TradingMode

logger = logging.getLogger(__name__)


def _create_strategy_components(
    strategy_id: str,
    symbol: str,
    trading_mode: TradingMode,
    store: Any,
    event_bus: Any,
    exchange: Any,
    settings: AppSettings,
) -> dict[str, Any]:
    """Create per-strategy components for a single strategy.

    Returns a dict of named components to register in AppOrchestrator.
    """
    preset = STRATEGY_PRESETS.get(strategy_id)
    if preset is None:
        logger.warning("Strategy '%s' not found, using default", strategy_id)
        preset = STRATEGY_PRESETS["default"]

    signal_gen = SignalGenerator(
        strategy_id=strategy_id,
        scoring_mode=preset.scoring_mode,
        entry_mode=preset.entry_mode,
        score_weights=preset.score_weights,
        tf_weights=preset.tf_weights,
        buy_threshold=preset.buy_threshold,
        sell_threshold=preset.sell_threshold,
        majority_min=preset.majority_min,
        use_daily_gate=preset.use_daily_gate,
        macro_weight=preset.macro_weight,
    )

    cb = CircuitBreaker(
        failure_threshold=settings.trading.max_consecutive_losses,
    )
    order_mgr = OrderManager(
        data_store=store,
        event_bus=event_bus,
        exchange_client=exchange,
        trading_mode=trading_mode,
        circuit_breaker=cb,
    )
    pos_mgr = PositionManager(data_store=store, event_bus=event_bus)
    risk_mgr = RiskManager(data_store=store, event_bus=event_bus)
    state_machine = StateMachine(
        strategy_id=strategy_id,
        trading_mode=trading_mode,
        data_store=store,
        event_bus=event_bus,
    )
    regime_mgr = RegimeSwitchManager()
    regime_mgr.set_initial_preset(strategy_id)

    loop = TradingLoop(
        strategy_id=strategy_id,
        symbol=symbol,
        signal_generator=signal_gen,
        order_manager=order_mgr,
        position_manager=pos_mgr,
        risk_manager=risk_mgr,
        state_machine=state_machine,
        event_bus=event_bus,
        data_store=store,
        exchange_client=exchange,
        trading_mode=trading_mode,
        regime_switch_manager=regime_mgr,
    )

    return {
        "signal_generator": signal_gen,
        "order_manager": order_mgr,
        "position_manager": pos_mgr,
        "risk_manager": risk_mgr,
        "state_machine": state_machine,
        "trading_loop": loop,
    }


async def bootstrap(
    settings: AppSettings | None = None,
    data_store: object | None = None,
) -> AppOrchestrator:
    """Create and wire all engine components.

    Supports multiple strategy IDs. When multiple strategies are active,
    per-strategy components are registered with suffix (e.g., "trading_loop:STR-001").
    For single strategy, components keep their original names for backward compat.

    Args:
        settings: Application settings. Defaults to env-based AppSettings.
        data_store: Optional pre-created DataStore (for testing with SqliteDataStore).

    Returns:
        Fully wired AppOrchestrator ready to run.
    """
    settings = settings or AppSettings()
    app = AppOrchestrator(settings)

    trading_mode = TradingMode(settings.trading.mode)
    strategy_ids = settings.trading.get_active_strategy_ids()
    symbol = settings.trading.symbols[0] if settings.trading.symbols else "BTC/KRW"
    multi_strategy = len(strategy_ids) > 1

    logger.info(
        "Bootstrapping engine: strategies=%s, mode=%s, symbol=%s",
        strategy_ids, trading_mode, symbol,
    )

    # ── Shared components ───────────────────────────────────────

    # [1] DataStore
    if data_store is not None:
        store = data_store
    else:
        from engine.data import create_data_store
        store = create_data_store(settings.db)

    app.register("datastore", store)

    # [2] Exchange client (shared — one API connection)
    exchange = UpbitExchangeClient(
        access_key=settings.exchange.api_key or None,
        secret_key=settings.exchange.api_secret or None,
    )
    app.register("exchange", exchange)

    # [3] Telegram notifications
    from engine.notification import NotificationBridge
    from engine.notification.telegram import TelegramNotifier

    notifier = TelegramNotifier(
        bot_token=settings.telegram.bot_token or None,
        chat_id=settings.telegram.chat_id or None,
        enabled=settings.telegram.enabled,
    )
    bridge = NotificationBridge(notifier)
    bridge.subscribe_all(app.event_bus)
    app.register("notifier", notifier)
    app.register("notification_bridge", bridge)

    # ── Per-strategy components ─────────────────────────────────

    trading_loops: dict[str, TradingLoop] = {}

    for sid in strategy_ids:
        components = _create_strategy_components(
            strategy_id=sid,
            symbol=symbol,
            trading_mode=trading_mode,
            store=store,
            event_bus=app.event_bus,
            exchange=exchange,
            settings=settings,
        )

        # Register with strategy suffix for multi, plain names for single
        for name, comp in components.items():
            key = f"{name}:{sid}" if multi_strategy else name
            app.register(key, comp)

        loop = components["trading_loop"]
        trading_loops[sid] = loop

        # Wire event subscriptions for this strategy's components
        _wire_event_subscriptions(
            app.event_bus,
            components["position_manager"],
            components["risk_manager"],
            components["trading_loop"],
        )

    # Store trading loops map on app for multi-strategy access
    app.register("trading_loops", trading_loops)

    # [8] MacroCollector — fetch macro indicators every 5 minutes
    macro_collector = MacroCollector(data_store=store)
    app.register("macro_collector", macro_collector)

    # [9] IPCServer with command routing
    ipc = IPCServer(app.event_bus, store)
    ipc.set_command_handler(_make_command_handler(trading_loops))
    app.register("ipc_server", ipc)

    logger.info(
        "Bootstrap complete — %d strategies, %d components registered",
        len(strategy_ids), len(app.components),
    )
    return app


def _wire_event_subscriptions(event_bus, pos_mgr, risk_mgr, trading_loop) -> None:
    """Subscribe event handlers for a strategy's components."""
    from shared.events import (
        MarketTickEvent,
        OrderFilledEvent,
        PositionClosedEvent,
        StopLossTriggeredEvent,
        TakeProfitTriggeredEvent,
    )

    event_bus.subscribe(OrderFilledEvent, pos_mgr.on_order_filled)
    event_bus.subscribe(MarketTickEvent, pos_mgr.on_market_tick)
    event_bus.subscribe(OrderFilledEvent, risk_mgr.on_order_filled)
    event_bus.subscribe(PositionClosedEvent, risk_mgr.on_position_closed)
    event_bus.subscribe(StopLossTriggeredEvent, trading_loop._on_stop_loss_triggered)
    event_bus.subscribe(TakeProfitTriggeredEvent, trading_loop._on_take_profit_triggered)
    event_bus.subscribe(PositionClosedEvent, trading_loop._on_position_closed)


def _make_command_handler(trading_loops: dict[str, TradingLoop]):
    """Create an IPC command handler that routes to the correct TradingLoop."""

    async def handler(command: str, strategy_id: str, params: dict) -> None:
        if strategy_id:
            # Route to specific strategy
            loop = trading_loops.get(strategy_id)
            if loop is None:
                logger.warning("Command for unknown strategy: %s", strategy_id)
                return
            await loop._handle_command(command, params)
        else:
            # Broadcast to all strategies (e.g., emergency_exit)
            for sid, loop in trading_loops.items():
                logger.info("Broadcasting command '%s' to %s", command, sid)
                await loop._handle_command(command, params)

    return handler


async def bootstrap_and_run(settings: AppSettings | None = None) -> None:
    """Bootstrap and run the engine (convenience entry point)."""
    app = await bootstrap(settings)

    trading_loops: dict[str, TradingLoop] = app.get("trading_loops")

    for sid, loop in trading_loops.items():
        await loop.start()
        app.scheduler.add_interval_job(
            loop.tick,
            seconds=loop._tick_interval,
            job_id=f"trading-tick-{sid}",
        )
        logger.info("Registered scheduler job for strategy %s", sid)

    # Macro collector — run immediately then every 5 minutes
    macro_collector: MacroCollector = app.get("macro_collector")
    await macro_collector.collect()
    app.scheduler.add_interval_job(
        macro_collector.collect,
        seconds=300,
        job_id="macro-collect",
    )
    logger.info("Registered macro collector job (every 5m)")

    await app.run()
