"""Order Manager — idempotent order execution pipeline.

Pipeline (Round 4 §7.1):
1. Idempotency check
2. Risk pre-validation (CB + RiskEngine)
3. Execute order (Paper or Live)
4. DB record
5. Confirmation loop (Live only, 3 retries × 3s)
6. Slippage recording
7. OrderFilledEvent publish
8. CircuitBreaker update
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from engine.execution.circuit_breaker import CircuitBreaker
from shared.enums import OrderSide, OrderStatus, OrderType, TradingMode
from shared.events import OrderFilledEvent, OrderRequestEvent, RiskAlertEvent
from shared.models import Order, PaperBalance

logger = logging.getLogger(__name__)

# Confirmation loop constants
CONFIRM_MAX_RETRIES = 3
CONFIRM_INTERVAL_SECONDS = 3.0


@dataclass
class OrderResult:
    success: bool
    order: Order | None = None
    reason: str = ""


class OrderManager:
    """Handles order lifecycle: validate → execute → confirm → record."""

    def __init__(
        self,
        data_store: object,
        event_bus: object,
        exchange_client: object | None = None,
        trading_mode: TradingMode = TradingMode.PAPER,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._store = data_store
        self._bus = event_bus
        self._exchange = exchange_client
        self._mode = trading_mode
        self._cb = circuit_breaker or CircuitBreaker()
        self._processed_keys: set[str] = set()

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._cb

    async def handle_order_request(
        self,
        event: OrderRequestEvent,
        risk_check: object | None = None,
    ) -> OrderResult:
        """Full pipeline for an incoming OrderRequestEvent."""

        # [1] Idempotency check
        if event.idempotency_key in self._processed_keys:
            logger.warning("Duplicate idempotency_key=%s, skipping", event.idempotency_key)
            return OrderResult(success=False, reason="duplicate_idempotency_key")
        self._processed_keys.add(event.idempotency_key)

        # [2] CircuitBreaker check
        if not self._cb.allow_request():
            logger.warning("CircuitBreaker OPEN, rejecting order for %s", event.strategy_id)
            await self._publish_risk_alert(
                event.strategy_id,
                "circuit_breaker_open",
                "Order rejected: circuit breaker is open",
            )
            return OrderResult(success=False, reason="circuit_breaker_open")

        # [2b] Risk pre-validation (optional external check)
        if risk_check is not None:
            allowed, reason = await self._run_risk_check(risk_check, event)
            if not allowed:
                return OrderResult(success=False, reason=reason)

        # [3] Execute order
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        if self._mode == TradingMode.PAPER:
            result = await self._execute_paper(event, order_id, now)
        else:
            result = await self._execute_live(event, order_id, now)

        if not result.success:
            self._cb.record_failure()
            return result

        assert result.order is not None

        # [8] CB success
        self._cb.record_success()

        # [4] DB record
        await self._store.save_order(result.order)

        # [7] Publish OrderFilledEvent
        slippage = float(result.order.slippage_pct or 0)
        filled_event = OrderFilledEvent(
            order_id=result.order.id,
            strategy_id=event.strategy_id,
            symbol=event.symbol,
            side=event.side,
            amount=event.amount,
            actual_price=result.order.price,
            slippage_pct=slippage,
        )
        await self._bus.publish(filled_event)

        return result

    # ── Paper execution ─────────────────────────────────────────────

    async def _execute_paper(
        self,
        event: OrderRequestEvent,
        order_id: str,
        now: datetime,
    ) -> OrderResult:
        """Paper mode: instant fill against internal balance."""
        balance: PaperBalance | None = await self._store.get_paper_balance(
            event.strategy_id
        )
        if balance is None:
            return OrderResult(success=False, reason="no_paper_balance")

        # Simulate price: use a simple 0% slippage for paper
        # In production, could add random slippage
        price = await self._get_current_price(event.symbol)
        if price is None:
            return OrderResult(success=False, reason="price_unavailable")

        # Check balance sufficiency
        cost = price * event.amount
        if event.side == OrderSide.BUY:
            if balance.krw < cost:
                return OrderResult(success=False, reason="insufficient_krw")
            new_balance = PaperBalance(
                strategy_id=event.strategy_id,
                krw=balance.krw - cost,
                btc=balance.btc + event.amount,
                initial_krw=balance.initial_krw,
            )
        else:
            if balance.btc < event.amount:
                return OrderResult(success=False, reason="insufficient_btc")
            new_balance = PaperBalance(
                strategy_id=event.strategy_id,
                krw=balance.krw + cost,
                btc=balance.btc - event.amount,
                initial_krw=balance.initial_krw,
            )

        await self._store.save_paper_balance(new_balance)

        order = Order(
            id=order_id,
            strategy_id=event.strategy_id,
            symbol=event.symbol,
            side=event.side,
            order_type=event.order_type,
            amount=event.amount,
            price=price,
            status=OrderStatus.FILLED,
            idempotency_key=event.idempotency_key,
            created_at=now,
            slippage_pct=Decimal("0"),
            filled_at=now,
        )
        return OrderResult(success=True, order=order)

    # ── Live execution ──────────────────────────────────────────────

    async def _execute_live(
        self,
        event: OrderRequestEvent,
        order_id: str,
        now: datetime,
    ) -> OrderResult:
        """Live mode: submit to exchange, run confirmation loop."""
        if self._exchange is None:
            return OrderResult(success=False, reason="no_exchange_client")

        try:
            resp = await self._exchange.create_order(
                symbol=event.symbol,
                side=event.side,
                order_type=event.order_type,
                amount=event.amount,
            )
        except Exception:
            logger.exception("Exchange create_order failed for %s", event.strategy_id)
            return OrderResult(success=False, reason="exchange_error")

        exchange_order_id = resp.get("id", order_id)

        # Save as pending
        pending_order = Order(
            id=exchange_order_id,
            strategy_id=event.strategy_id,
            symbol=event.symbol,
            side=event.side,
            order_type=event.order_type,
            amount=event.amount,
            price=Decimal(str(resp.get("price", 0))),
            status=OrderStatus.PENDING,
            idempotency_key=event.idempotency_key,
            created_at=now,
        )
        await self._store.save_order(pending_order)

        # [5] Confirmation loop
        filled_order = await self._confirmation_loop(
            exchange_order_id, event, pending_order
        )
        if filled_order is None:
            return OrderResult(success=False, reason="order_not_filled")

        return OrderResult(success=True, order=filled_order)

    async def _confirmation_loop(
        self,
        exchange_order_id: str,
        event: OrderRequestEvent,
        pending_order: Order,
    ) -> Order | None:
        """Poll exchange for fill status up to 3 times with 3s intervals."""
        for attempt in range(CONFIRM_MAX_RETRIES):
            await asyncio.sleep(CONFIRM_INTERVAL_SECONDS)
            try:
                resp = await self._exchange.fetch_order(exchange_order_id, event.symbol)
            except Exception:
                logger.exception("fetch_order failed attempt %d", attempt + 1)
                continue

            status = resp.get("status", "")
            if status == "filled" or status == OrderStatus.FILLED:
                actual_price = Decimal(str(resp.get("price", pending_order.price)))
                expected_price = pending_order.price
                if expected_price and expected_price > 0:
                    slippage = abs(actual_price - expected_price) / expected_price * 100
                else:
                    slippage = Decimal("0")

                return Order(
                    id=pending_order.id,
                    strategy_id=pending_order.strategy_id,
                    symbol=pending_order.symbol,
                    side=pending_order.side,
                    order_type=pending_order.order_type,
                    amount=pending_order.amount,
                    price=actual_price,
                    status=OrderStatus.FILLED,
                    idempotency_key=pending_order.idempotency_key,
                    created_at=pending_order.created_at,
                    slippage_pct=slippage,
                    filled_at=datetime.now(timezone.utc),
                )

            if status in ("cancelled", "failed"):
                logger.warning("Order %s status=%s", exchange_order_id, status)
                return None

        logger.warning(
            "Order %s not filled after %d retries",
            exchange_order_id,
            CONFIRM_MAX_RETRIES,
        )
        return None

    # ── Helpers ──────────────────────────────────────────────────────

    async def _get_current_price(self, symbol: str) -> Decimal | None:
        """Get current price. Paper mode uses exchange ticker if available."""
        if self._exchange is not None:
            try:
                ticker = await self._exchange.fetch_ticker(symbol)
                return Decimal(str(ticker.get("last", ticker.get("price", 0))))
            except Exception:
                pass
        return None

    async def _run_risk_check(
        self, risk_check: object, event: OrderRequestEvent
    ) -> tuple[bool, str]:
        """Run external risk check function. Expects callable(event) -> (bool, str)."""
        try:
            result = await risk_check(event)  # type: ignore[operator]
            if isinstance(result, tuple):
                return result
            return (True, "")
        except Exception:
            logger.exception("Risk check failed")
            return (False, "risk_check_error")

    async def _publish_risk_alert(
        self, strategy_id: str, alert_type: str, message: str
    ) -> None:
        from shared.enums import AlertSeverity

        alert = RiskAlertEvent(
            strategy_id=strategy_id,
            alert_type=alert_type,
            message=message,
            severity=AlertSeverity.WARNING,
        )
        await self._bus.publish(alert)
