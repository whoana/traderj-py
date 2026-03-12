"""E2E integration test — full trade cycle.

Tests the complete signal → order → position → close flow:
1. Signal generated (BUY)
2. OrderManager executes paper order
3. PositionManager opens position
4. Market tick updates unrealized PnL
5. Signal generated (SELL)
6. OrderManager executes sell order
7. PositionManager closes position with realized PnL
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from engine.data.sqlite_store import SqliteDataStore
from engine.execution.order_manager import OrderManager
from engine.execution.position_manager import PositionManager
from engine.loop.event_bus import EventBus
from shared.enums import OrderSide, OrderType, TradingMode
from shared.events import MarketTickEvent, OrderFilledEvent, OrderRequestEvent
from shared.models import PaperBalance


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
    """Minimal fake exchange for paper-mode price lookup."""

    class FakeExchange:
        def __init__(self):
            self.price = Decimal("90000000")  # 90M KRW

        async def fetch_ticker(self, symbol: str):
            return {"last": str(self.price)}

    return FakeExchange()


@pytest.fixture
async def order_manager(store, bus, exchange):
    return OrderManager(
        data_store=store,
        event_bus=bus,
        exchange_client=exchange,
        trading_mode=TradingMode.PAPER,
    )


@pytest.fixture
async def position_manager(store, bus):
    return PositionManager(data_store=store, event_bus=bus)


async def test_full_trade_cycle(store, bus, exchange, order_manager, position_manager):
    """BUY → hold → price change → SELL → verify PnL."""
    strategy_id = "test-strat-1"
    symbol = "BTC/KRW"

    # Setup initial paper balance: 10M KRW
    initial = PaperBalance(
        strategy_id=strategy_id,
        krw=Decimal("10000000"),
        btc=Decimal("0"),
        initial_krw=Decimal("10000000"),
    )
    await store.save_paper_balance(initial)

    # Subscribe PositionManager to OrderFilledEvent
    filled_events: list[OrderFilledEvent] = []

    async def capture_and_handle(event: OrderFilledEvent):
        filled_events.append(event)
        await position_manager.on_order_filled(event)

    bus.subscribe(OrderFilledEvent, capture_and_handle)

    # ── Step 1: BUY order ────────────────────────────────────────
    buy_request = OrderRequestEvent(
        strategy_id=strategy_id,
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),  # 0.01 BTC
        idempotency_key="buy-001",
    )

    result = await order_manager.handle_order_request(buy_request)
    assert result.success, f"BUY failed: {result.reason}"
    assert result.order is not None
    assert result.order.price == Decimal("90000000")

    # Drain event bus
    await asyncio.sleep(0.1)  # let event bus process

    # Verify OrderFilledEvent was published and handled
    assert len(filled_events) == 1
    assert filled_events[0].side == OrderSide.BUY

    # Verify position opened
    pos = position_manager.get_position(strategy_id)
    assert pos is not None
    assert pos.entry_price == Decimal("90000000")
    assert pos.amount == Decimal("0.01")

    # Verify paper balance updated
    balance = await store.get_paper_balance(strategy_id)
    assert balance is not None
    assert balance.btc == Decimal("0.01")
    expected_krw = Decimal("10000000") - Decimal("90000000") * Decimal("0.01")
    assert balance.krw == expected_krw

    # ── Step 2: Market tick — price goes up ───────────────────────
    exchange.price = Decimal("95000000")  # +5M per BTC
    tick = MarketTickEvent(
        symbol=symbol,
        price=Decimal("95000000"),
        bid=Decimal("94990000"),
        ask=Decimal("95010000"),
        volume_24h=Decimal("100"),
    )
    await position_manager.on_market_tick(tick)

    pos = position_manager.get_position(strategy_id)
    assert pos is not None
    # Unrealized PnL = (95M - 90M) × 0.01 = 50,000 KRW
    assert pos.unrealized_pnl == Decimal("50000")
    assert pos.current_price == Decimal("95000000")

    # ── Step 3: SELL order ───────────────────────────────────────
    exchange.price = Decimal("95000000")
    sell_request = OrderRequestEvent(
        strategy_id=strategy_id,
        symbol=symbol,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        idempotency_key="sell-001",
    )

    result = await order_manager.handle_order_request(sell_request)
    assert result.success, f"SELL failed: {result.reason}"

    await asyncio.sleep(0.1)  # let event bus process

    # Verify position closed
    assert len(filled_events) == 2
    assert filled_events[1].side == OrderSide.SELL

    pos = position_manager.get_position(strategy_id)
    assert pos is None  # closed

    # Verify final paper balance
    balance = await store.get_paper_balance(strategy_id)
    assert balance is not None
    assert balance.btc == Decimal("0")
    # Profit = (95M - 90M) × 0.01 = 50K KRW
    expected_final_krw = expected_krw + Decimal("95000000") * Decimal("0.01")
    assert balance.krw == expected_final_krw

    # ── Step 4: Verify DB persistence ────────────────────────────
    orders = await store.get_orders(strategy_id=strategy_id)
    assert len(orders) == 2
    assert orders[0].side == OrderSide.SELL  # most recent first
    assert orders[1].side == OrderSide.BUY

    positions = await store.get_positions(strategy_id=strategy_id)
    assert len(positions) == 1
    assert positions[0].realized_pnl == Decimal("50000")


async def test_idempotency_blocks_duplicate(store, bus, exchange, order_manager):
    """Same idempotency_key should be rejected on second attempt."""
    strategy_id = "test-strat-2"
    await store.save_paper_balance(
        PaperBalance(
            strategy_id=strategy_id,
            krw=Decimal("10000000"),
            btc=Decimal("0"),
            initial_krw=Decimal("10000000"),
        )
    )

    request = OrderRequestEvent(
        strategy_id=strategy_id,
        symbol="BTC/KRW",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        idempotency_key="dup-key-001",
    )

    r1 = await order_manager.handle_order_request(request)
    assert r1.success

    r2 = await order_manager.handle_order_request(request)
    assert not r2.success
    assert r2.reason == "duplicate_idempotency_key"


async def test_circuit_breaker_blocks_after_failures(store, bus, order_manager):
    """CircuitBreaker should open after consecutive failures."""
    strategy_id = "test-strat-3"
    # No paper balance → will fail with "no_paper_balance"
    cb = order_manager.circuit_breaker

    for i in range(cb.failure_threshold):
        r = await order_manager.handle_order_request(
            OrderRequestEvent(
                strategy_id=strategy_id,
                symbol="BTC/KRW",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                amount=Decimal("0.01"),
                idempotency_key=f"cb-test-{i}",
            )
        )
        assert not r.success

    # Next request should be blocked by circuit breaker
    r = await order_manager.handle_order_request(
        OrderRequestEvent(
            strategy_id=strategy_id,
            symbol="BTC/KRW",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
            idempotency_key="cb-blocked",
        )
    )
    assert not r.success
    assert r.reason == "circuit_breaker_open"
