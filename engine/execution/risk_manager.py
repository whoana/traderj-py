"""Execution-level Risk Manager — pre-trade validation and state persistence.

Bridges strategy/risk.py (ATR-based decisions) with the execution pipeline:
- Pre-validates every OrderRequest against risk limits
- Persists RiskState to DataStore after each trade
- Publishes RiskAlertEvent on limit breaches
- Integrates with OrderManager as a gate before execution
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from engine.strategy.risk import RiskConfig, RiskDecision, RiskEngine
from shared.enums import AlertSeverity, OrderSide
from shared.events import (
    OrderFilledEvent,
    PositionClosedEvent,
    RiskAlertEvent,
    RiskStateEvent,
)
from shared.models import RiskState

logger = logging.getLogger(__name__)


class RiskManager:
    """Execution-level risk manager with DB persistence and EventBus integration."""

    def __init__(
        self,
        data_store: object,
        event_bus: object,
        config: RiskConfig | None = None,
    ) -> None:
        self._store = data_store
        self._bus = event_bus
        self._engines: dict[str, RiskEngine] = {}
        self._default_config = config or RiskConfig()
        self._last_decision: dict[str, RiskDecision] = {}

    def get_engine(self, strategy_id: str) -> RiskEngine:
        if strategy_id not in self._engines:
            self._engines[strategy_id] = RiskEngine(
                config=self._default_config, strategy_id=strategy_id
            )
        return self._engines[strategy_id]

    async def load_state(self, strategy_id: str) -> None:
        """Load persisted risk state from DB."""
        state = await self._store.get_risk_state(strategy_id)
        if state:
            engine = self.get_engine(strategy_id)
            engine.consecutive_losses = state.consecutive_losses
            engine.daily_pnl = float(state.daily_pnl)
            engine.cooldown_until = state.cooldown_until
            logger.info(
                "Loaded risk state for %s: losses=%d, daily_pnl=%.0f",
                strategy_id,
                state.consecutive_losses,
                float(state.daily_pnl),
            )

    async def save_state(self, strategy_id: str) -> None:
        """Persist current risk state to DB."""
        engine = self.get_engine(strategy_id)
        state = RiskState(
            strategy_id=strategy_id,
            consecutive_losses=engine.consecutive_losses,
            daily_pnl=Decimal(str(engine.daily_pnl)),
            last_updated=datetime.now(UTC),
            cooldown_until=engine.cooldown_until,
        )
        await self._store.save_risk_state(state)

    async def pre_validate(
        self,
        strategy_id: str,
        side: OrderSide,
        total_balance_krw: float,
        current_price: float,
        current_atr: float,
        existing_position_krw: float = 0.0,
    ) -> tuple[bool, str, float]:
        """Pre-validate an order request against risk limits.

        Returns:
            (allowed, reason, suggested_position_krw)
        """
        if side == OrderSide.SELL:
            return True, "sell_always_allowed", 0.0

        engine = self.get_engine(strategy_id)
        decision = engine.evaluate_buy(
            total_balance_krw=total_balance_krw,
            current_price=current_price,
            current_atr=current_atr,
            existing_position_krw=existing_position_krw,
        )

        if not decision.allowed:
            await self._publish_risk_alert(
                strategy_id, "order_blocked", decision.reason
            )

        # Store latest decision for use by trading loop
        self._last_decision[strategy_id] = decision

        return decision.allowed, decision.reason, decision.position_size_krw

    def get_last_decision(self, strategy_id: str):
        """Get the most recent RiskDecision for a strategy."""
        return self._last_decision.get(strategy_id)

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        """Update risk state after order fill (subscribes to OrderFilledEvent)."""
        engine = self.get_engine(event.strategy_id)
        await self._publish_risk_state(event.strategy_id, engine)

    async def on_position_closed(self, event: PositionClosedEvent) -> None:
        """Record trade result and update risk state after position close."""
        engine = self.get_engine(event.strategy_id)
        pnl = float(event.realized_pnl)
        engine.record_trade_result(pnl)

        if pnl < 0 and engine.consecutive_losses >= engine.config.max_consecutive_losses:
            await self._publish_risk_alert(
                event.strategy_id,
                "cooldown_activated",
                f"consecutive_losses={engine.consecutive_losses}",
            )

        await self.save_state(event.strategy_id)
        await self._publish_risk_state(event.strategy_id, engine)

    async def _publish_risk_alert(
        self, strategy_id: str, alert_type: str, message: str
    ) -> None:
        severity = AlertSeverity.WARNING
        if "cooldown" in alert_type or "daily_loss_limit" in message:
            severity = AlertSeverity.CRITICAL

        event = RiskAlertEvent(
            strategy_id=strategy_id,
            alert_type=alert_type,
            message=message,
            severity=severity,
        )
        await self._bus.publish(event)
        logger.warning("Risk alert [%s] %s: %s", strategy_id, alert_type, message)

    async def _publish_risk_state(
        self, strategy_id: str, engine: RiskEngine
    ) -> None:
        event = RiskStateEvent(
            strategy_id=strategy_id,
            consecutive_losses=engine.consecutive_losses,
            daily_pnl=engine.daily_pnl,
            position_pct=0.0,
            atr_pct=0.0,
            volatility_status="normal",
            cooldown_until=engine.cooldown_until,
        )
        await self._bus.publish(event)
