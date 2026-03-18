"""Tests for PositionManager."""

from decimal import Decimal

import pytest

from engine.execution.position_manager import PositionManager
from shared.enums import OrderSide, PositionStatus
from shared.events import (
    MarketTickEvent,
    OrderFilledEvent,
    PositionClosedEvent,
    PositionOpenedEvent,
    StopLossTriggeredEvent,
    TakeProfitTriggeredEvent,
    TrailingStopUpdatedEvent,
)
from shared.models import Position


# ── Fakes ────────────────────────────────────────────────────────────


class FakeDataStore:
    def __init__(self):
        self.positions: list[Position] = []
        self._open_positions: list[Position] = []

    async def save_position(self, position: Position) -> None:
        self.positions.append(position)

    async def get_positions(
        self, strategy_id: str | None = None, status: str | None = None
    ) -> list[Position]:
        return [
            p
            for p in self._open_positions
            if (status is None or p.status == status)
        ]


class FakeEventBus:
    def __init__(self):
        self.events: list[object] = []

    async def publish(self, event: object) -> None:
        self.events.append(event)


# ── Helpers ──────────────────────────────────────────────────────────


def make_fill(
    strategy_id: str = "STR-001",
    side: OrderSide = OrderSide.BUY,
    price: float = 95_000_000,
    amount: float = 0.001,
) -> OrderFilledEvent:
    return OrderFilledEvent(
        order_id="ord-1",
        strategy_id=strategy_id,
        symbol="BTC/KRW",
        side=side,
        amount=Decimal(str(amount)),
        actual_price=Decimal(str(price)),
        slippage_pct=0.0,
    )


def make_tick(
    symbol: str = "BTC/KRW",
    price: float = 96_000_000,
) -> MarketTickEvent:
    return MarketTickEvent(
        symbol=symbol,
        price=Decimal(str(price)),
        bid=Decimal(str(price - 100)),
        ask=Decimal(str(price + 100)),
        volume_24h=Decimal("1000"),
    )


# ── Open/Close Tests ────────────────────────────────────────────────


class TestPositionOpen:
    @pytest.mark.asyncio
    async def test_open_position_on_buy_fill(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY))

        assert pm.has_open_position("STR-001")
        pos = pm.get_position("STR-001")
        assert pos is not None
        assert pos.entry_price == Decimal("95000000")
        assert pos.status == PositionStatus.OPEN

        opened = [e for e in bus.events if isinstance(e, PositionOpenedEvent)]
        assert len(opened) == 1
        assert opened[0].entry_price == Decimal("95000000")

    @pytest.mark.asyncio
    async def test_duplicate_open_skipped(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY))
        await pm.on_order_filled(make_fill(side=OrderSide.BUY))

        opened = [e for e in bus.events if isinstance(e, PositionOpenedEvent)]
        assert len(opened) == 1  # second open skipped

    @pytest.mark.asyncio
    async def test_position_saved_to_store(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY))
        assert len(store.positions) == 1


class TestPositionClose:
    @pytest.mark.asyncio
    async def test_close_position_on_sell_fill(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.on_order_filled(make_fill(side=OrderSide.SELL, price=96_000_000))

        assert not pm.has_open_position("STR-001")

        closed = [e for e in bus.events if isinstance(e, PositionClosedEvent)]
        assert len(closed) == 1
        # PnL = (96M - 95M) * 0.001 = 1000
        assert closed[0].realized_pnl == Decimal("1000.000")

    @pytest.mark.asyncio
    async def test_close_nonexistent(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.SELL))
        closed = [e for e in bus.events if isinstance(e, PositionClosedEvent)]
        assert len(closed) == 0  # no position to close

    @pytest.mark.asyncio
    async def test_realized_pnl_loss(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.on_order_filled(make_fill(side=OrderSide.SELL, price=94_000_000))

        closed = [e for e in bus.events if isinstance(e, PositionClosedEvent)]
        assert closed[0].realized_pnl == Decimal("-1000.000")


# ── PnL Tracking Tests ──────────────────────────────────────────────


class TestPnLTracking:
    @pytest.mark.asyncio
    async def test_unrealized_pnl_positive(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.on_market_tick(make_tick(price=96_000_000))

        pos = pm.get_position("STR-001")
        assert pos is not None
        # (96M - 95M) * 0.001 = 1000
        assert pos.unrealized_pnl == Decimal("1000.000")
        assert pos.current_price == Decimal("96000000")

    @pytest.mark.asyncio
    async def test_unrealized_pnl_negative(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.on_market_tick(make_tick(price=94_000_000))

        pos = pm.get_position("STR-001")
        assert pos is not None
        assert pos.unrealized_pnl == Decimal("-1000.000")

    @pytest.mark.asyncio
    async def test_tick_unrelated_symbol_ignored(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY))
        await pm.on_market_tick(make_tick(symbol="ETH/KRW", price=5_000_000))

        pos = pm.get_position("STR-001")
        assert pos is not None
        assert pos.unrealized_pnl == Decimal("0")  # unchanged


# ── Stop Loss Tests ──────────────────────────────────────────────────


class TestStopLoss:
    @pytest.mark.asyncio
    async def test_stop_loss_triggered(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.set_stop_loss("STR-001", Decimal("94_500_000"))

        await pm.on_market_tick(make_tick(price=94_400_000))

        stops = [e for e in bus.events if isinstance(e, StopLossTriggeredEvent)]
        assert len(stops) == 1
        assert stops[0].trigger_price == Decimal("94400000")

    @pytest.mark.asyncio
    async def test_stop_loss_not_triggered_above(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.set_stop_loss("STR-001", Decimal("94_500_000"))

        await pm.on_market_tick(make_tick(price=94_600_000))

        stops = [e for e in bus.events if isinstance(e, StopLossTriggeredEvent)]
        assert len(stops) == 0

    @pytest.mark.asyncio
    async def test_set_stop_loss(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY))
        result = await pm.set_stop_loss("STR-001", Decimal("93_000_000"))
        assert result is True

        pos = pm.get_position("STR-001")
        assert pos is not None
        assert pos.stop_loss == Decimal("93000000")

    @pytest.mark.asyncio
    async def test_set_stop_loss_no_position(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        result = await pm.set_stop_loss("UNKNOWN", Decimal("90_000_000"))
        assert result is False


# ── Load from DB Tests ───────────────────────────────────────────────


class TestLoadPositions:
    @pytest.mark.asyncio
    async def test_load_open_positions(self):
        from datetime import datetime, timezone

        store = FakeDataStore()
        bus = FakeEventBus()

        existing = Position(
            id="pos-1",
            strategy_id="STR-001",
            symbol="BTC/KRW",
            side=OrderSide.BUY,
            amount=Decimal("0.001"),
            entry_price=Decimal("95000000"),
            current_price=Decimal("95000000"),
            stop_loss=None,
            trailing_stop=None,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            status=PositionStatus.OPEN,
            opened_at=datetime.now(timezone.utc),
        )
        store._open_positions = [existing]

        pm = PositionManager(data_store=store, event_bus=bus)
        await pm.load_open_positions()

        assert pm.has_open_position("STR-001")
        assert pm.get_position("STR-001") is not None


# ── Take Profit Tests ────────────────────────────────────────────────


class TestTakeProfit:
    @pytest.mark.asyncio
    async def test_take_profit_triggered(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.set_take_profit("STR-001", Decimal("97_000_000"))

        await pm.on_market_tick(make_tick(price=97_100_000))

        tps = [e for e in bus.events if isinstance(e, TakeProfitTriggeredEvent)]
        assert len(tps) == 1
        assert tps[0].trigger_price == Decimal("97100000")
        assert tps[0].take_profit_price == Decimal("97000000")

    @pytest.mark.asyncio
    async def test_take_profit_not_triggered_below(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.set_take_profit("STR-001", Decimal("97_000_000"))

        await pm.on_market_tick(make_tick(price=96_500_000))

        tps = [e for e in bus.events if isinstance(e, TakeProfitTriggeredEvent)]
        assert len(tps) == 0

    @pytest.mark.asyncio
    async def test_set_take_profit(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY))
        result = await pm.set_take_profit("STR-001", Decimal("99_000_000"))
        assert result is True

        pos = pm.get_position("STR-001")
        assert pos is not None
        assert pos.take_profit == Decimal("99000000")

    @pytest.mark.asyncio
    async def test_set_take_profit_no_position(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        result = await pm.set_take_profit("UNKNOWN", Decimal("99_000_000"))
        assert result is False

    @pytest.mark.asyncio
    async def test_tp_has_priority_over_sl(self):
        """When both TP and SL conditions are met, TP fires (price rose above TP)."""
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        await pm.set_take_profit("STR-001", Decimal("97_000_000"))
        # SL not set, so only TP fires
        await pm.on_market_tick(make_tick(price=97_500_000))

        tps = [e for e in bus.events if isinstance(e, TakeProfitTriggeredEvent)]
        stops = [e for e in bus.events if isinstance(e, StopLossTriggeredEvent)]
        assert len(tps) == 1
        assert len(stops) == 0


# ── Trailing Stop Tests ──────────────────────────────────────────────


class TestTrailingStop:
    @pytest.mark.asyncio
    async def test_trailing_stop_activation_and_update(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))

        # Configure: activate at 96M, trail at 1.5%
        pm.configure_trailing_stop(
            "STR-001",
            activation_price=Decimal("96_000_000"),
            distance_pct=0.015,
        )

        # Price below activation → no trailing stop
        await pm.on_market_tick(make_tick(price=95_500_000))
        pos = pm.get_position("STR-001")
        assert pos.trailing_stop is None

        # Price at activation → trailing stop activates
        await pm.on_market_tick(make_tick(price=96_000_000))
        pos = pm.get_position("STR-001")
        assert pos.trailing_stop is not None
        # Trailing stop = 96M * (1 - 0.015) = 94_560_000
        expected_ts = Decimal("96000000") * (1 - Decimal("0.015"))
        assert pos.trailing_stop == expected_ts

        updates = [e for e in bus.events if isinstance(e, TrailingStopUpdatedEvent)]
        assert len(updates) == 1

    @pytest.mark.asyncio
    async def test_trailing_stop_moves_up_with_price(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        pm.configure_trailing_stop(
            "STR-001",
            activation_price=Decimal("96_000_000"),
            distance_pct=0.015,
        )

        # Activate
        await pm.on_market_tick(make_tick(price=96_000_000))
        ts1 = pm.get_position("STR-001").trailing_stop

        # Price rises → trailing stop rises
        await pm.on_market_tick(make_tick(price=97_000_000))
        ts2 = pm.get_position("STR-001").trailing_stop
        assert ts2 > ts1

        # Price drops (but above trailing stop) → trailing stop stays
        await pm.on_market_tick(make_tick(price=96_500_000))
        ts3 = pm.get_position("STR-001").trailing_stop
        assert ts3 == ts2

    @pytest.mark.asyncio
    async def test_trailing_stop_triggers_stop_loss(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        pm.configure_trailing_stop(
            "STR-001",
            activation_price=Decimal("96_000_000"),
            distance_pct=0.015,
        )

        # Activate and move up
        await pm.on_market_tick(make_tick(price=97_000_000))
        ts = pm.get_position("STR-001").trailing_stop
        # ts = 97M * 0.985 = 95_545_000

        # Price drops below trailing stop
        await pm.on_market_tick(make_tick(price=95_500_000))

        stops = [e for e in bus.events if isinstance(e, StopLossTriggeredEvent)]
        assert len(stops) == 1

    @pytest.mark.asyncio
    async def test_configure_trailing_stop_no_position(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        result = pm.configure_trailing_stop(
            "UNKNOWN",
            activation_price=Decimal("96_000_000"),
            distance_pct=0.015,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_trailing_state_cleared_on_close(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        pm = PositionManager(data_store=store, event_bus=bus)

        await pm.on_order_filled(make_fill(side=OrderSide.BUY, price=95_000_000))
        pm.configure_trailing_stop(
            "STR-001",
            activation_price=Decimal("96_000_000"),
            distance_pct=0.015,
        )
        assert "STR-001" in pm._trailing_state

        await pm.on_order_filled(make_fill(side=OrderSide.SELL, price=96_000_000))
        assert "STR-001" not in pm._trailing_state


# ── Risk Engine TP/SL Tests ──────────────────────────────────────────


class TestRiskDecisionTPSL:
    def test_take_profit_calculated_with_rr_ratio(self):
        from engine.strategy.risk import RiskConfig, RiskEngine

        config = RiskConfig(
            use_atr_stop=True,
            atr_stop_multiplier=2.0,
            reward_risk_ratio=2.0,
            use_take_profit=True,
        )
        engine = RiskEngine(config=config)
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=95_000_000,
            current_atr=2_000_000,  # ATR = 2M
        )
        assert decision.allowed is True
        # SL = 95M - 2*2M = 91M
        assert decision.stop_loss_price == 91_000_000
        # Risk = 95M - 91M = 4M, TP = 95M + 4M*2 = 103M
        assert decision.take_profit_price == 103_000_000

    def test_trailing_stop_activation_calculated(self):
        from engine.strategy.risk import RiskConfig, RiskEngine

        config = RiskConfig(trailing_stop_activation_pct=0.01)
        engine = RiskEngine(config=config)
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=100_000_000,
            current_atr=2_000_000,
        )
        assert decision.allowed is True
        # Activation = 100M * 1.01 = 101M
        assert decision.trailing_stop_activation == 101_000_000
