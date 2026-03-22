"""Tests for StateMachine, OHLCVCollector, MacroCollector."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.data.macro import MacroCollector
from engine.data.ohlcv import OHLCVCollector
from engine.loop.state import (
    ACTIVE_STATES,
    TRANSITIONS,
    InvalidTransitionError,
    StateMachine,
)
from shared.enums import BotStateEnum, TradingMode
from shared.events import BotStateChangeEvent, OHLCVUpdateEvent
from shared.models import BotStateModel, Candle, MacroSnapshot


# ── Fakes ────────────────────────────────────────────────────────────


class FakeDataStore:
    def __init__(self):
        self.bot_states: dict[str, BotStateModel] = {}
        self.candles_upserted: list[Candle] = []
        self.macro_snapshots: list[MacroSnapshot] = []

    async def get_bot_state(self, strategy_id: str) -> BotStateModel | None:
        return self.bot_states.get(strategy_id)

    async def save_bot_state(self, model: BotStateModel) -> None:
        self.bot_states[model.strategy_id] = model

    async def upsert_candles(self, candles: list[Candle]) -> int:
        self.candles_upserted.extend(candles)
        return len(candles)

    async def save_macro_snapshot(self, snapshot: MacroSnapshot) -> None:
        self.macro_snapshots.append(snapshot)


class FakeEventBus:
    def __init__(self):
        self.events: list[object] = []

    async def publish(self, event: object) -> None:
        self.events.append(event)


class FakeExchangeClient:
    def __init__(self, candles: list[Candle] | None = None):
        self._candles = candles or []

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 200
    ) -> list[Candle]:
        return self._candles


# ── StateMachine Tests ───────────────────────────────────────────────


class TestStateMachineInit:
    @pytest.mark.asyncio
    async def test_initial_state(self):
        sm = StateMachine("STR-001", TradingMode.PAPER, FakeDataStore(), FakeEventBus())
        assert sm.state == BotStateEnum.IDLE
        assert sm.is_idle is True
        assert sm.is_active is False

    @pytest.mark.asyncio
    async def test_load_persisted_state(self):
        store = FakeDataStore()
        store.bot_states["STR-001"] = BotStateModel(
            strategy_id="STR-001",
            state=BotStateEnum.SCANNING,
            trading_mode=TradingMode.PAPER,
            last_updated=datetime.now(timezone.utc),
        )
        sm = StateMachine("STR-001", TradingMode.PAPER, store, FakeEventBus())
        loaded = await sm.load_state()
        assert loaded == BotStateEnum.SCANNING
        assert sm.state == BotStateEnum.SCANNING

    @pytest.mark.asyncio
    async def test_load_no_persisted_state(self):
        sm = StateMachine("NEW", TradingMode.PAPER, FakeDataStore(), FakeEventBus())
        loaded = await sm.load_state()
        assert loaded == BotStateEnum.IDLE


class TestStateMachineTransitions:
    @pytest.mark.asyncio
    async def test_valid_transition(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        sm = StateMachine("STR-001", TradingMode.PAPER, store, bus)

        await sm.transition(BotStateEnum.STARTING, "user_start")
        assert sm.state == BotStateEnum.STARTING

        events = [e for e in bus.events if isinstance(e, BotStateChangeEvent)]
        assert len(events) == 1
        assert events[0].old_state == BotStateEnum.IDLE
        assert events[0].new_state == BotStateEnum.STARTING

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        sm = StateMachine("STR-001", TradingMode.PAPER, FakeDataStore(), FakeEventBus())
        with pytest.raises(InvalidTransitionError):
            await sm.transition(BotStateEnum.EXECUTING)

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        sm = StateMachine("STR-001", TradingMode.PAPER, store, bus)

        lifecycle = [
            BotStateEnum.STARTING,
            BotStateEnum.SCANNING,
            BotStateEnum.VALIDATING,
            BotStateEnum.EXECUTING,
            BotStateEnum.LOGGING,
            BotStateEnum.MONITORING,
            BotStateEnum.SCANNING,  # loop back
            BotStateEnum.PAUSED,
            BotStateEnum.SHUTTING_DOWN,
            BotStateEnum.IDLE,
        ]
        for target in lifecycle:
            await sm.transition(target)

        assert sm.state == BotStateEnum.IDLE
        assert len(bus.events) == len(lifecycle)

    @pytest.mark.asyncio
    async def test_state_persisted(self):
        store = FakeDataStore()
        sm = StateMachine("STR-001", TradingMode.PAPER, store, FakeEventBus())

        await sm.transition(BotStateEnum.STARTING)
        assert "STR-001" in store.bot_states
        assert store.bot_states["STR-001"].state == BotStateEnum.STARTING

    @pytest.mark.asyncio
    async def test_is_active(self):
        sm = StateMachine("STR-001", TradingMode.PAPER, FakeDataStore(), FakeEventBus())
        assert sm.is_active is False

        await sm.transition(BotStateEnum.STARTING)
        assert sm.is_active is False

        await sm.transition(BotStateEnum.SCANNING)
        assert sm.is_active is True


class TestForceState:
    @pytest.mark.asyncio
    async def test_force_bypasses_validation(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        sm = StateMachine("STR-001", TradingMode.PAPER, store, bus)

        # IDLE → EXECUTING is normally invalid
        await sm.force_state(BotStateEnum.EXECUTING, "recovery")
        assert sm.state == BotStateEnum.EXECUTING

        events = [e for e in bus.events if isinstance(e, BotStateChangeEvent)]
        assert len(events) == 1
        assert "FORCE" in events[0].reason

    @pytest.mark.asyncio
    async def test_force_persists(self):
        store = FakeDataStore()
        sm = StateMachine("STR-001", TradingMode.PAPER, store, FakeEventBus())
        await sm.force_state(BotStateEnum.IDLE)
        assert store.bot_states["STR-001"].state == BotStateEnum.IDLE


class TestTransitionMap:
    def test_all_states_have_transitions(self):
        for state in BotStateEnum:
            assert state in TRANSITIONS, f"Missing transitions for {state}"

    def test_shutting_down_reachable_from_active(self):
        for state in ACTIVE_STATES:
            assert BotStateEnum.SHUTTING_DOWN in TRANSITIONS[state]


# ── OHLCVCollector Tests ─────────────────────────────────────────────


class TestOHLCVCollector:
    @pytest.mark.asyncio
    async def test_collect_stores_and_publishes(self):
        candle = Candle(
            time=datetime.now(timezone.utc),
            symbol="BTC/KRW",
            timeframe="1h",
            open=Decimal("95000000"),
            high=Decimal("96000000"),
            low=Decimal("94000000"),
            close=Decimal("95500000"),
            volume=Decimal("100"),
        )
        exchange = FakeExchangeClient(candles=[candle])
        store = FakeDataStore()
        bus = FakeEventBus()

        collector = OHLCVCollector(exchange, store, bus, symbol="BTC/KRW")
        count = await collector.collect("1h")

        assert count == 1
        assert len(store.candles_upserted) == 1
        events = [e for e in bus.events if isinstance(e, OHLCVUpdateEvent)]
        assert len(events) == 1
        assert events[0].timeframe == "1h"

    @pytest.mark.asyncio
    async def test_collect_empty(self):
        exchange = FakeExchangeClient(candles=[])
        store = FakeDataStore()
        bus = FakeEventBus()

        collector = OHLCVCollector(exchange, store, bus)
        count = await collector.collect("1h")
        assert count == 0

    @pytest.mark.asyncio
    async def test_collect_all_timeframes(self):
        candle = Candle(
            time=datetime.now(timezone.utc),
            symbol="BTC/KRW",
            timeframe="1h",
            open=Decimal("95000000"),
            high=Decimal("96000000"),
            low=Decimal("94000000"),
            close=Decimal("95500000"),
            volume=Decimal("100"),
        )
        exchange = FakeExchangeClient(candles=[candle])
        store = FakeDataStore()
        bus = FakeEventBus()

        collector = OHLCVCollector(exchange, store, bus)
        results = await collector.collect_all_timeframes(["1h", "4h"])
        assert results["1h"] == 1
        assert results["4h"] == 1

    @pytest.mark.asyncio
    async def test_collect_exchange_error(self):
        class FailExchange:
            async def fetch_ohlcv(self, **kwargs):
                raise ConnectionError("timeout")

        store = FakeDataStore()
        bus = FakeEventBus()
        collector = OHLCVCollector(FailExchange(), store, bus)
        count = await collector.collect("1h")
        assert count == 0


# ── MacroCollector Tests ─────────────────────────────────────────────


class TestMacroCollector:
    @pytest.mark.asyncio
    async def test_collect_disabled(self):
        store = FakeDataStore()
        collector = MacroCollector(data_store=store, enabled=False)
        snapshot = await collector.collect()

        assert snapshot is None
        assert len(store.macro_snapshots) == 0

    @pytest.mark.asyncio
    async def test_collect_fetches_data(self):
        store = FakeDataStore()
        collector = MacroCollector(data_store=store)
        snapshot = await collector.collect()

        assert snapshot is not None
        assert 0 <= snapshot.fear_greed <= 100
        assert -1.0 <= snapshot.market_score <= 1.0
        assert len(store.macro_snapshots) == 1

    def test_calculate_market_score_extremes(self):
        # Extreme greed + high funding + low dominance
        score = MacroCollector._calculate_market_score(
            fear_greed=100,
            funding_rate=0.05,
            btc_dominance=30,
        )
        assert score > 0.5  # bullish

        # Extreme fear + negative funding + high dominance
        score = MacroCollector._calculate_market_score(
            fear_greed=0,
            funding_rate=-0.05,
            btc_dominance=70,
        )
        assert score < -0.5  # bearish
