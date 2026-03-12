"""Tests for OrderManager."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from engine.execution.circuit_breaker import CBState, CircuitBreaker
from engine.execution.order_manager import OrderManager
from shared.enums import (
    AlertSeverity,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingMode,
)
from shared.events import OrderFilledEvent, OrderRequestEvent, RiskAlertEvent
from shared.models import Order, PaperBalance


# ── Fakes ────────────────────────────────────────────────────────────


class FakeDataStore:
    def __init__(self):
        self.orders: list[Order] = []
        self.balances: dict[str, PaperBalance] = {}

    async def save_order(self, order: Order) -> None:
        self.orders.append(order)

    async def get_paper_balance(self, strategy_id: str) -> PaperBalance | None:
        return self.balances.get(strategy_id)

    async def save_paper_balance(self, balance: PaperBalance) -> None:
        self.balances[balance.strategy_id] = balance


class FakeEventBus:
    def __init__(self):
        self.events: list[object] = []

    async def publish(self, event: object) -> None:
        self.events.append(event)


class FakeExchangeClient:
    def __init__(self, ticker_price: float = 95_000_000):
        self.ticker_price = ticker_price
        self.orders_created: list[dict] = []
        self.fetch_responses: list[dict] = []
        self._fetch_call = 0

    async def fetch_ticker(self, symbol: str) -> dict:
        return {"last": self.ticker_price}

    async def create_order(self, **kwargs) -> dict:
        resp = {"id": "exch-001", "price": self.ticker_price, "status": "pending"}
        self.orders_created.append(resp)
        return resp

    async def fetch_order(self, order_id: str, symbol: str) -> dict:
        idx = min(self._fetch_call, len(self.fetch_responses) - 1)
        resp = self.fetch_responses[idx]
        self._fetch_call += 1
        return resp


# ── Helpers ──────────────────────────────────────────────────────────


def make_event(
    strategy_id: str = "STR-001",
    side: OrderSide = OrderSide.BUY,
    amount: str = "0.001",
    key: str | None = None,
) -> OrderRequestEvent:
    return OrderRequestEvent(
        strategy_id=strategy_id,
        symbol="BTC/KRW",
        side=side,
        amount=Decimal(amount),
        order_type=OrderType.MARKET,
        idempotency_key=key or f"key-{id(object())}",
    )


def setup_paper_balance(store: FakeDataStore, strategy_id: str = "STR-001"):
    store.balances[strategy_id] = PaperBalance(
        strategy_id=strategy_id,
        krw=Decimal("10_000_000"),
        btc=Decimal("0.1"),
        initial_krw=Decimal("10_000_000"),
    )


# ── Paper Mode Tests ─────────────────────────────────────────────────


class TestOrderManagerPaper:
    @pytest.fixture
    def setup(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
        )
        setup_paper_balance(store)
        return om, store, bus

    @pytest.mark.asyncio
    async def test_buy_success(self, setup):
        om, store, bus = setup
        event = make_event(side=OrderSide.BUY, amount="0.001", key="buy-1")
        result = await om.handle_order_request(event)

        assert result.success is True
        assert result.order is not None
        assert result.order.status == OrderStatus.FILLED
        assert result.order.side == OrderSide.BUY

        # Balance updated
        bal = store.balances["STR-001"]
        assert bal.btc == Decimal("0.1") + Decimal("0.001")

        # OrderFilledEvent published
        filled = [e for e in bus.events if isinstance(e, OrderFilledEvent)]
        assert len(filled) == 1
        assert filled[0].side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_sell_success(self, setup):
        om, store, bus = setup
        event = make_event(side=OrderSide.SELL, amount="0.01", key="sell-1")
        result = await om.handle_order_request(event)

        assert result.success is True
        bal = store.balances["STR-001"]
        assert bal.btc == Decimal("0.1") - Decimal("0.01")

    @pytest.mark.asyncio
    async def test_insufficient_krw(self, setup):
        om, store, bus = setup
        event = make_event(side=OrderSide.BUY, amount="1.0", key="big-buy")
        result = await om.handle_order_request(event)

        assert result.success is False
        assert result.reason == "insufficient_krw"

    @pytest.mark.asyncio
    async def test_insufficient_btc(self, setup):
        om, store, bus = setup
        event = make_event(side=OrderSide.SELL, amount="1.0", key="big-sell")
        result = await om.handle_order_request(event)

        assert result.success is False
        assert result.reason == "insufficient_btc"

    @pytest.mark.asyncio
    async def test_no_paper_balance(self, setup):
        om, store, bus = setup
        event = make_event(strategy_id="UNKNOWN", key="no-bal")
        result = await om.handle_order_request(event)
        assert result.success is False
        assert result.reason == "no_paper_balance"

    @pytest.mark.asyncio
    async def test_order_saved_to_store(self, setup):
        om, store, bus = setup
        event = make_event(key="save-1")
        await om.handle_order_request(event)
        assert len(store.orders) == 1
        assert store.orders[0].idempotency_key == "save-1"


# ── Idempotency Tests ────────────────────────────────────────────────


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_duplicate_key_rejected(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
        )
        setup_paper_balance(store)

        event1 = make_event(key="dup-key")
        event2 = make_event(key="dup-key")

        r1 = await om.handle_order_request(event1)
        r2 = await om.handle_order_request(event2)

        assert r1.success is True
        assert r2.success is False
        assert r2.reason == "duplicate_idempotency_key"

    @pytest.mark.asyncio
    async def test_different_keys_both_succeed(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
        )
        setup_paper_balance(store)

        r1 = await om.handle_order_request(make_event(key="k1"))
        r2 = await om.handle_order_request(make_event(key="k2"))

        assert r1.success is True
        assert r2.success is True


# ── CircuitBreaker Integration Tests ─────────────────────────────────


class TestOrderManagerCircuitBreaker:
    @pytest.mark.asyncio
    async def test_cb_open_rejects(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()  # trips to OPEN

        om = OrderManager(
            data_store=store,
            event_bus=bus,
            trading_mode=TradingMode.PAPER,
            circuit_breaker=cb,
        )

        result = await om.handle_order_request(make_event(key="cb-1"))
        assert result.success is False
        assert result.reason == "circuit_breaker_open"

        # RiskAlertEvent published
        alerts = [e for e in bus.events if isinstance(e, RiskAlertEvent)]
        assert len(alerts) == 1
        assert alerts[0].alert_type == "circuit_breaker_open"

    @pytest.mark.asyncio
    async def test_successful_order_resets_cb(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.consecutive_failures == 2

        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
            circuit_breaker=cb,
        )
        setup_paper_balance(store)

        result = await om.handle_order_request(make_event(key="reset-1"))
        assert result.success is True
        assert cb.consecutive_failures == 0
        assert cb.state == CBState.CLOSED


# ── Risk Check Tests ─────────────────────────────────────────────────


class TestRiskCheck:
    @pytest.mark.asyncio
    async def test_risk_check_reject(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
        )
        setup_paper_balance(store)

        async def reject_all(event):
            return (False, "daily_loss_exceeded")

        result = await om.handle_order_request(make_event(key="risk-1"), risk_check=reject_all)
        assert result.success is False
        assert result.reason == "daily_loss_exceeded"

    @pytest.mark.asyncio
    async def test_risk_check_pass(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
        )
        setup_paper_balance(store)

        async def allow_all(event):
            return (True, "")

        result = await om.handle_order_request(make_event(key="risk-2"), risk_check=allow_all)
        assert result.success is True


# ── Live Mode Tests ──────────────────────────────────────────────────


class TestOrderManagerLive:
    @pytest.fixture(autouse=True)
    def _fast_confirm(self, monkeypatch):
        import engine.execution.order_manager as om_mod
        monkeypatch.setattr(om_mod, "CONFIRM_INTERVAL_SECONDS", 0.01)

    @pytest.mark.asyncio
    async def test_live_fill(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient(ticker_price=95_000_000)
        exchange.fetch_responses = [
            {"status": "filled", "price": 95_050_000}
        ]

        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.LIVE,
        )

        event = make_event(key="live-1")
        result = await om.handle_order_request(event)

        assert result.success is True
        assert result.order is not None
        assert result.order.status == OrderStatus.FILLED

        filled = [e for e in bus.events if isinstance(e, OrderFilledEvent)]
        assert len(filled) == 1

    @pytest.mark.asyncio
    async def test_live_not_filled(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        exchange.fetch_responses = [
            {"status": "pending"},
            {"status": "pending"},
            {"status": "pending"},
        ]

        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.LIVE,
        )

        event = make_event(key="live-timeout")
        result = await om.handle_order_request(event)

        assert result.success is False
        assert result.reason == "order_not_filled"

    @pytest.mark.asyncio
    async def test_live_cancelled(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient()
        exchange.fetch_responses = [{"status": "cancelled"}]

        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.LIVE,
        )

        event = make_event(key="live-cancel")
        result = await om.handle_order_request(event)

        assert result.success is False
        assert result.reason == "order_not_filled"

    @pytest.mark.asyncio
    async def test_live_no_exchange(self):
        store = FakeDataStore()
        bus = FakeEventBus()

        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=None,
            trading_mode=TradingMode.LIVE,
        )

        event = make_event(key="no-exch")
        result = await om.handle_order_request(event)

        assert result.success is False
        assert result.reason == "no_exchange_client"


# ── Slippage Tests ───────────────────────────────────────────────────


class TestSlippage:
    @pytest.mark.asyncio
    async def test_paper_zero_slippage(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient(ticker_price=95_000_000)
        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.PAPER,
        )
        setup_paper_balance(store)

        result = await om.handle_order_request(make_event(key="slip-0"))
        assert result.order is not None
        assert result.order.slippage_pct == Decimal("0")

    @pytest.mark.asyncio
    async def test_live_slippage_calculated(self):
        store = FakeDataStore()
        bus = FakeEventBus()
        exchange = FakeExchangeClient(ticker_price=95_000_000)
        exchange.fetch_responses = [
            {"status": "filled", "price": 95_095_000}  # 0.1% slippage
        ]

        om = OrderManager(
            data_store=store,
            event_bus=bus,
            exchange_client=exchange,
            trading_mode=TradingMode.LIVE,
        )

        event = make_event(key="slip-calc")
        result = await om.handle_order_request(event)

        assert result.success is True
        assert result.order is not None
        assert result.order.slippage_pct is not None
        assert float(result.order.slippage_pct) > 0
