"""Unit tests for TradingLoop — main trading cycle.

Uses mock exchange and SQLite in-memory store.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from engine.data.sqlite_store import SqliteDataStore
from engine.execution.order_manager import OrderManager
from engine.execution.position_manager import PositionManager
from engine.execution.risk_manager import RiskManager
from engine.loop.event_bus import EventBus
from engine.loop.state import StateMachine
from engine.loop.trading_loop import TradingLoop
from engine.strategy.presets import STRATEGY_PRESETS
from engine.strategy.signal import SignalGenerator
from shared.enums import (
    BotStateEnum,
    SignalDirection,
    TradingMode,
)
from shared.events import OrderFilledEvent
from shared.models import Candle, PaperBalance

# ── Fixtures ─────────────────────────────────────────────────────


class FakeExchange:
    """Minimal exchange mock that returns deterministic OHLCV + ticker."""

    def __init__(self, price: float = 90_000_000.0):
        self.price = price
        self.fetch_ticker_count = 0
        self.fetch_ohlcv_count = 0

    async def fetch_ticker(self, symbol: str) -> dict:
        self.fetch_ticker_count += 1
        return {
            "last": str(self.price),
            "bid": str(self.price - 10000),
            "ask": str(self.price + 10000),
            "volume": "100",
        }

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        self.fetch_ohlcv_count += 1
        candles = []
        base = self.price
        for i in range(limit):
            # Unique timestamps: each candle 1 hour apart
            t = datetime(2024, 1, 1, tzinfo=UTC) + __import__("datetime").timedelta(hours=i)
            # Add slight price variation to generate meaningful indicators
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


@pytest.fixture
async def bus():
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def exchange():
    return FakeExchange()


@pytest.fixture
def preset():
    return STRATEGY_PRESETS["STR-001"]


@pytest.fixture
def signal_gen(preset):
    return SignalGenerator(
        strategy_id="STR-001",
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


@pytest.fixture
async def trading_loop(store, bus, exchange, signal_gen):
    """Create a fully wired TradingLoop with mock components."""
    order_mgr = OrderManager(
        data_store=store,
        event_bus=bus,
        exchange_client=exchange,
        trading_mode=TradingMode.PAPER,
    )
    pos_mgr = PositionManager(data_store=store, event_bus=bus)
    risk_mgr = RiskManager(data_store=store, event_bus=bus)
    state_machine = StateMachine(
        strategy_id="STR-001",
        trading_mode=TradingMode.PAPER,
        data_store=store,
        event_bus=bus,
    )

    # Wire event subscriptions
    bus.subscribe(OrderFilledEvent, pos_mgr.on_order_filled)

    loop = TradingLoop(
        strategy_id="STR-001",
        symbol="BTC/KRW",
        signal_generator=signal_gen,
        order_manager=order_mgr,
        position_manager=pos_mgr,
        risk_manager=risk_mgr,
        state_machine=state_machine,
        event_bus=bus,
        data_store=store,
        exchange_client=exchange,
        trading_mode=TradingMode.PAPER,
    )
    return loop


# ── Tests ────────────────────────────────────────────────────────


async def test_start_transitions_to_scanning(trading_loop):
    """start() should transition from IDLE to SCANNING."""
    assert trading_loop._state.state == BotStateEnum.IDLE
    await trading_loop.start()
    assert trading_loop._state.state == BotStateEnum.SCANNING
    assert trading_loop.is_running


async def test_stop_transitions_to_idle(trading_loop):
    """stop() should transition from active to IDLE."""
    await trading_loop.start()
    assert trading_loop._state.state == BotStateEnum.SCANNING

    await trading_loop.stop()
    assert trading_loop._state.state == BotStateEnum.IDLE
    assert not trading_loop.is_running


async def test_pause_and_resume(trading_loop):
    """pause/resume should correctly transition states."""
    await trading_loop.start()
    assert trading_loop._state.state == BotStateEnum.SCANNING

    await trading_loop.pause()
    assert trading_loop._state.state == BotStateEnum.PAUSED

    await trading_loop.resume()
    assert trading_loop._state.state == BotStateEnum.SCANNING


async def test_tick_generates_signal(trading_loop, store):
    """A single tick should generate a signal and save it to DB."""
    # Setup paper balance
    await store.save_paper_balance(PaperBalance(
        strategy_id="STR-001",
        krw=Decimal("10000000"),
        btc=Decimal("0"),
        initial_krw=Decimal("10000000"),
    ))

    await trading_loop.start()
    signal = await trading_loop.tick()

    assert signal is not None
    assert signal.direction in (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD)
    assert trading_loop.tick_count == 1

    # Verify signal was saved to DB
    signals = await store.get_signals(strategy_id="STR-001")
    assert len(signals) >= 1


async def test_tick_skipped_when_paused(trading_loop, store):
    """tick() should return None when bot is paused."""
    await store.save_paper_balance(PaperBalance(
        strategy_id="STR-001",
        krw=Decimal("10000000"),
        btc=Decimal("0"),
        initial_krw=Decimal("10000000"),
    ))
    await trading_loop.start()
    await trading_loop.pause()

    signal = await trading_loop.tick()
    assert signal is None
    assert trading_loop.tick_count == 0  # tick was skipped so count not incremented


async def test_tick_skipped_when_not_running(trading_loop):
    """tick() should return None when loop not started."""
    signal = await trading_loop.tick()
    assert signal is None


async def test_ensure_paper_balance(trading_loop, store):
    """start() should create paper balance if not exists."""
    await trading_loop.start()
    balance = await store.get_paper_balance("STR-001")
    assert balance is not None
    assert balance.krw > 0


async def test_emergency_exit(trading_loop, store, bus):
    """emergency_exit should stop the loop and force IDLE state."""
    await store.save_paper_balance(PaperBalance(
        strategy_id="STR-001",
        krw=Decimal("10000000"),
        btc=Decimal("0"),
        initial_krw=Decimal("10000000"),
    ))
    await trading_loop.start()
    assert trading_loop.is_running

    await trading_loop._emergency_exit()
    assert not trading_loop.is_running
    assert trading_loop._state.state == BotStateEnum.IDLE


async def test_candles_to_df():
    """_candles_to_df should produce correct DataFrame."""
    candles = [
        Candle(
            time=datetime(2024, 1, 1, 0, tzinfo=UTC),
            symbol="BTC/KRW",
            timeframe="1h",
            open=Decimal("90000000"),
            high=Decimal("91000000"),
            low=Decimal("89000000"),
            close=Decimal("90500000"),
            volume=Decimal("10"),
        ),
        Candle(
            time=datetime(2024, 1, 1, 1, tzinfo=UTC),
            symbol="BTC/KRW",
            timeframe="1h",
            open=Decimal("90500000"),
            high=Decimal("92000000"),
            low=Decimal("90000000"),
            close=Decimal("91500000"),
            volume=Decimal("15"),
        ),
    ]
    df = TradingLoop._candles_to_df(candles)
    assert len(df) == 2
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.iloc[0]["close"] == 90_500_000.0


async def test_handle_command_pause(trading_loop, store):
    """_handle_command('pause') should pause the loop."""
    await store.save_paper_balance(PaperBalance(
        strategy_id="STR-001",
        krw=Decimal("10000000"),
        btc=Decimal("0"),
        initial_krw=Decimal("10000000"),
    ))
    await trading_loop.start()
    assert trading_loop._state.state == BotStateEnum.SCANNING

    await trading_loop._handle_command("pause", {})
    assert trading_loop._state.state == BotStateEnum.PAUSED


async def test_multiple_ticks(trading_loop, store):
    """Multiple ticks should increment tick_count."""
    await store.save_paper_balance(PaperBalance(
        strategy_id="STR-001",
        krw=Decimal("10000000"),
        btc=Decimal("0"),
        initial_krw=Decimal("10000000"),
    ))
    await trading_loop.start()

    for _ in range(3):
        await trading_loop.tick()
        # Wait for event bus processing
        await asyncio.sleep(0.05)

    assert trading_loop.tick_count == 3


# ── DCA/Grid regime reconfiguration tests ────────────────────────


class TestReconfigureDCAGrid:
    async def test_reconfigure_trending_creates_dca_only(self, store, bus, exchange, signal_gen):
        """Trending regime should create DCA engine but no Grid engine."""
        from engine.strategy.regime_switch import RegimeSwitchManager
        from shared.enums import RegimeType

        regime_mgr = RegimeSwitchManager()
        regime_mgr._current_regime = RegimeType.TRENDING_HIGH_VOL

        loop = TradingLoop(
            strategy_id="STR-001",
            symbol="BTC/KRW",
            signal_generator=signal_gen,
            order_manager=OrderManager(store, bus, exchange, TradingMode.PAPER),
            position_manager=PositionManager(store, bus),
            risk_manager=RiskManager(store, bus),
            state_machine=StateMachine("STR-001", TradingMode.PAPER, store, bus),
            event_bus=bus,
            data_store=store,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
            regime_switch_manager=regime_mgr,
        )

        loop._reconfigure_dca_grid(RegimeType.TRENDING_HIGH_VOL, 90_000_000.0)

        assert loop._dca_engine is not None
        assert loop._dca_engine.config.base_buy_krw == 150_000
        assert loop._grid_engine is None

    async def test_reconfigure_ranging_creates_both(self, store, bus, exchange, signal_gen):
        """Ranging regime should create both DCA and Grid engines."""
        from engine.strategy.regime_switch import RegimeSwitchManager
        from shared.enums import RegimeType

        regime_mgr = RegimeSwitchManager()
        loop = TradingLoop(
            strategy_id="STR-001",
            symbol="BTC/KRW",
            signal_generator=signal_gen,
            order_manager=OrderManager(store, bus, exchange, TradingMode.PAPER),
            position_manager=PositionManager(store, bus),
            risk_manager=RiskManager(store, bus),
            state_machine=StateMachine("STR-001", TradingMode.PAPER, store, bus),
            event_bus=bus,
            data_store=store,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
            regime_switch_manager=regime_mgr,
        )

        loop._reconfigure_dca_grid(RegimeType.RANGING_HIGH_VOL, 90_000_000.0)

        assert loop._dca_engine is not None
        assert loop._dca_engine.config.base_buy_krw == 70_000
        assert loop._grid_engine is not None
        assert loop._grid_engine.config.num_grids == 8

    async def test_regime_switch_deactivates_grid(self, store, bus, exchange, signal_gen):
        """Switching from ranging to trending should deactivate Grid."""
        from engine.strategy.regime_switch import RegimeSwitchManager
        from shared.enums import RegimeType

        regime_mgr = RegimeSwitchManager()
        loop = TradingLoop(
            strategy_id="STR-001",
            symbol="BTC/KRW",
            signal_generator=signal_gen,
            order_manager=OrderManager(store, bus, exchange, TradingMode.PAPER),
            position_manager=PositionManager(store, bus),
            risk_manager=RiskManager(store, bus),
            state_machine=StateMachine("STR-001", TradingMode.PAPER, store, bus),
            event_bus=bus,
            data_store=store,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
            regime_switch_manager=regime_mgr,
        )

        # First: ranging → grid active
        loop._reconfigure_dca_grid(RegimeType.RANGING_LOW_VOL, 90_000_000.0)
        assert loop._grid_engine is not None
        assert loop._grid_engine.config.num_grids == 12

        # Then: trending → grid deactivated
        loop._reconfigure_dca_grid(RegimeType.TRENDING_HIGH_VOL, 90_000_000.0)
        assert loop._grid_engine is None
        assert loop._dca_engine is not None
        assert loop._dca_engine.config.base_buy_krw == 150_000

    async def test_dca_state_preserved_on_reconfigure(self, store, bus, exchange, signal_gen):
        """DCA buy history should be preserved across regime switches."""
        from datetime import UTC, datetime

        from engine.strategy.regime_switch import RegimeSwitchManager
        from shared.enums import RegimeType

        regime_mgr = RegimeSwitchManager()
        loop = TradingLoop(
            strategy_id="STR-001",
            symbol="BTC/KRW",
            signal_generator=signal_gen,
            order_manager=OrderManager(store, bus, exchange, TradingMode.PAPER),
            position_manager=PositionManager(store, bus),
            risk_manager=RiskManager(store, bus),
            state_machine=StateMachine("STR-001", TradingMode.PAPER, store, bus),
            event_bus=bus,
            data_store=store,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
            regime_switch_manager=regime_mgr,
        )

        # Setup initial DCA with some history
        loop._reconfigure_dca_grid(RegimeType.TRENDING_HIGH_VOL, 90_000_000.0)
        buy_time = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
        loop._dca_engine.record_buy(150_000, now=buy_time)
        assert loop._dca_engine.buy_count == 1

        # Switch regime → DCA state preserved
        loop._reconfigure_dca_grid(RegimeType.RANGING_LOW_VOL, 90_000_000.0)
        assert loop._dca_engine.buy_count == 1
        assert loop._dca_engine.total_invested == 150_000
        assert loop._dca_engine._last_buy_time == buy_time

    async def test_no_regime_mgr_skips_reconfigure(self, store, bus, exchange, signal_gen):
        """No regime manager should silently skip reconfiguration."""
        from shared.enums import RegimeType

        loop = TradingLoop(
            strategy_id="STR-001",
            symbol="BTC/KRW",
            signal_generator=signal_gen,
            order_manager=OrderManager(store, bus, exchange, TradingMode.PAPER),
            position_manager=PositionManager(store, bus),
            risk_manager=RiskManager(store, bus),
            state_machine=StateMachine("STR-001", TradingMode.PAPER, store, bus),
            event_bus=bus,
            data_store=store,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
        )

        # Should not raise
        loop._reconfigure_dca_grid(RegimeType.TRENDING_HIGH_VOL, 90_000_000.0)
        assert loop._dca_engine is None
        assert loop._grid_engine is None

    async def test_get_last_close(self):
        """_get_last_close should return close from best available TF."""

        df_1h = pd.DataFrame(
            {"close": [90_000_000.0, 91_000_000.0]},
            index=pd.date_range("2024-01-01", periods=2, freq="h"),
        )
        df_4h = pd.DataFrame(
            {"close": [89_000_000.0, 92_000_000.0]},
            index=pd.date_range("2024-01-01", periods=2, freq="4h"),
        )

        assert TradingLoop._get_last_close({"1h": df_1h, "4h": df_4h}) == 91_000_000.0
        assert TradingLoop._get_last_close({"4h": df_4h}) == 92_000_000.0
        assert TradingLoop._get_last_close({}) == 0.0
