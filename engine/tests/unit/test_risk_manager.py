"""Unit tests for execution-level RiskManager.

Tests:
- Pre-validation (daily loss limit, cooldown, volatility cap)
- State persistence (load/save)
- Event handling (on_order_filled, on_position_closed)
- CircuitBreaker integration via consecutive losses
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from engine.data.sqlite_store import SqliteDataStore
from engine.execution.risk_manager import RiskManager
from engine.loop.event_bus import EventBus
from engine.strategy.risk import RiskConfig
from shared.enums import OrderSide
from shared.events import PositionClosedEvent, RiskAlertEvent


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
def risk_mgr(store, bus):
    config = RiskConfig(
        max_position_pct=0.20,
        daily_max_loss_pct=0.05,
        max_consecutive_losses=3,
        cooldown_hours=24,
        min_order_krw=5000,
        volatility_cap_pct=0.08,
    )
    return RiskManager(data_store=store, event_bus=bus, config=config)


class TestPreValidation:
    async def test_buy_approved(self, risk_mgr):
        """Normal buy should be approved."""
        allowed, reason, size = await risk_mgr.pre_validate(
            strategy_id="STR-001",
            side=OrderSide.BUY,
            total_balance_krw=10_000_000,
            current_price=90_000_000,
            current_atr=2_000_000,
        )
        assert allowed
        assert reason == "approved"
        assert size > 0

    async def test_sell_always_allowed(self, risk_mgr):
        """SELL side should always pass validation."""
        allowed, reason, _ = await risk_mgr.pre_validate(
            strategy_id="STR-001",
            side=OrderSide.SELL,
            total_balance_krw=10_000_000,
            current_price=90_000_000,
            current_atr=2_000_000,
        )
        assert allowed
        assert reason == "sell_always_allowed"

    async def test_daily_loss_limit_blocks(self, risk_mgr):
        """Should block buy when daily loss exceeds limit."""
        engine = risk_mgr.get_engine("STR-001")
        # Simulate daily loss of 6% (limit is 5%)
        engine.daily_pnl = -600_000
        engine.daily_date = datetime.now(UTC).strftime("%Y-%m-%d")

        allowed, reason, _ = await risk_mgr.pre_validate(
            strategy_id="STR-001",
            side=OrderSide.BUY,
            total_balance_krw=10_000_000,
            current_price=90_000_000,
            current_atr=2_000_000,
        )
        assert not allowed
        assert "daily_loss_limit" in reason

    async def test_volatility_cap_blocks(self, risk_mgr):
        """Should block buy when ATR/price exceeds volatility cap."""
        allowed, reason, _ = await risk_mgr.pre_validate(
            strategy_id="STR-001",
            side=OrderSide.BUY,
            total_balance_krw=10_000_000,
            current_price=90_000_000,
            current_atr=90_000_000 * 0.10,  # 10% ATR > 8% cap
        )
        assert not allowed
        assert "volatility_cap" in reason

    async def test_cooldown_blocks(self, risk_mgr):
        """Should block buy during cooldown period."""
        engine = risk_mgr.get_engine("STR-001")
        engine.cooldown_until = datetime.now(UTC) + timedelta(hours=12)

        allowed, reason, _ = await risk_mgr.pre_validate(
            strategy_id="STR-001",
            side=OrderSide.BUY,
            total_balance_krw=10_000_000,
            current_price=90_000_000,
            current_atr=2_000_000,
        )
        assert not allowed
        assert "cooldown_active" in reason


class TestStatePersistence:
    async def test_save_and_load_state(self, risk_mgr, store):
        """Risk state should round-trip through DB."""
        engine = risk_mgr.get_engine("STR-001")
        engine.consecutive_losses = 2
        engine.daily_pnl = -100_000

        await risk_mgr.save_state("STR-001")

        # Create new manager, load state
        new_mgr = RiskManager(data_store=store, event_bus=EventBus())
        await new_mgr.load_state("STR-001")

        new_engine = new_mgr.get_engine("STR-001")
        assert new_engine.consecutive_losses == 2
        assert new_engine.daily_pnl == -100_000

    async def test_load_nonexistent_state(self, risk_mgr):
        """Loading state for unknown strategy should be a no-op."""
        await risk_mgr.load_state("NONEXISTENT")
        engine = risk_mgr.get_engine("NONEXISTENT")
        assert engine.consecutive_losses == 0


class TestEventHandling:
    async def test_on_position_closed_records_loss(self, risk_mgr):
        """on_position_closed with negative PnL should increment losses."""
        event = PositionClosedEvent(
            position_id="pos-1",
            strategy_id="STR-001",
            symbol="BTC/KRW",
            realized_pnl=Decimal("-50000"),
            exit_reason="signal_sell",
        )
        await risk_mgr.on_position_closed(event)

        engine = risk_mgr.get_engine("STR-001")
        assert engine.consecutive_losses == 1
        assert engine.daily_pnl == -50000

    async def test_on_position_closed_records_win(self, risk_mgr):
        """on_position_closed with positive PnL should reset losses."""
        # First record a loss
        engine = risk_mgr.get_engine("STR-001")
        engine.consecutive_losses = 2

        event = PositionClosedEvent(
            position_id="pos-2",
            strategy_id="STR-001",
            symbol="BTC/KRW",
            realized_pnl=Decimal("100000"),
            exit_reason="signal_sell",
        )
        await risk_mgr.on_position_closed(event)

        assert engine.consecutive_losses == 0

    async def test_consecutive_losses_trigger_cooldown(self, risk_mgr):
        """3 consecutive losses should activate cooldown."""
        for i in range(3):
            event = PositionClosedEvent(
                position_id=f"pos-{i}",
                strategy_id="STR-001",
                symbol="BTC/KRW",
                realized_pnl=Decimal("-30000"),
                exit_reason="signal_sell",
            )
            await risk_mgr.on_position_closed(event)

        engine = risk_mgr.get_engine("STR-001")
        assert engine.consecutive_losses == 3
        assert engine.cooldown_until is not None
        assert engine.cooldown_until > datetime.now(UTC)

    async def test_risk_alert_published_on_cooldown(self, risk_mgr, bus):
        """RiskAlertEvent should be published when cooldown activates."""
        alerts: list[RiskAlertEvent] = []

        async def capture(event: RiskAlertEvent):
            alerts.append(event)

        bus.subscribe(RiskAlertEvent, capture)

        for i in range(3):
            event = PositionClosedEvent(
                position_id=f"pos-{i}",
                strategy_id="STR-001",
                symbol="BTC/KRW",
                realized_pnl=Decimal("-30000"),
                exit_reason="signal_sell",
            )
            await risk_mgr.on_position_closed(event)

        # Wait for event processing
        import asyncio
        await asyncio.sleep(0.1)

        assert len(alerts) >= 1
        assert any("cooldown" in a.alert_type for a in alerts)


class TestPositionSizing:
    async def test_position_size_respects_max(self, risk_mgr):
        """Position size should not exceed max_position_pct."""
        allowed, reason, size = await risk_mgr.pre_validate(
            strategy_id="STR-001",
            side=OrderSide.BUY,
            total_balance_krw=10_000_000,
            current_price=90_000_000,
            current_atr=100_000,  # very low ATR → would want large position
        )
        assert allowed
        # Max position = 20% of 10M = 2M
        assert size <= 10_000_000 * 0.20 + 1

    async def test_below_min_order_blocks(self, risk_mgr):
        """Position too small should be blocked."""
        allowed, reason, _ = await risk_mgr.pre_validate(
            strategy_id="STR-001",
            side=OrderSide.BUY,
            total_balance_krw=1000,  # very small balance
            current_price=90_000_000,
            current_atr=2_000_000,
        )
        assert not allowed
        assert reason == "below_min_order"
