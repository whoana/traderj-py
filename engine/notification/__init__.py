"""Notification subsystem — bridges EventBus events to TelegramNotifier."""

from __future__ import annotations

import logging
from typing import Any

from engine.notification.telegram import TelegramNotifier
from shared.events import (
    BotStateChangeEvent,
    OrderFilledEvent,
    PositionClosedEvent,
    RegimeChangeEvent,
    RiskAlertEvent,
    StopLossTriggeredEvent,
)

logger = logging.getLogger(__name__)


class NotificationBridge:
    """Subscribes to EventBus events and forwards them to TelegramNotifier."""

    def __init__(self, notifier: TelegramNotifier) -> None:
        self._notifier = notifier

    def subscribe_all(self, event_bus: Any) -> None:
        """Subscribe to relevant events on the EventBus."""
        event_bus.subscribe(OrderFilledEvent, self._on_order_filled)
        event_bus.subscribe(PositionClosedEvent, self._on_position_closed)
        event_bus.subscribe(RiskAlertEvent, self._on_risk_alert)
        event_bus.subscribe(BotStateChangeEvent, self._on_state_change)
        event_bus.subscribe(RegimeChangeEvent, self._on_regime_change)
        event_bus.subscribe(StopLossTriggeredEvent, self._on_stop_loss)
        logger.info("NotificationBridge subscribed to EventBus")

    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
        try:
            await self._notifier.send_trade_alert(
                strategy_id=event.strategy_id,
                side=event.side,
                amount=event.amount,
                price=event.actual_price,
            )
        except Exception:
            logger.exception("Failed to send trade alert")

    async def _on_position_closed(self, event: PositionClosedEvent) -> None:
        try:
            pnl = event.realized_pnl
            emoji = "\U0001f4b0" if pnl >= 0 else "\U0001f4b8"
            await self._notifier._send(
                f"{emoji} <b>Position Closed</b>\n"
                f"Strategy: <code>{event.strategy_id}</code>\n"
                f"PnL: {pnl:+,.0f} KRW\n"
                f"Reason: {event.exit_reason}"
            )
        except Exception:
            logger.exception("Failed to send position closed alert")

    async def _on_risk_alert(self, event: RiskAlertEvent) -> None:
        try:
            await self._notifier.send_risk_alert(
                strategy_id=event.strategy_id,
                alert_type=event.alert_type,
                message=event.message,
            )
        except Exception:
            logger.exception("Failed to send risk alert")

    async def _on_state_change(self, event: BotStateChangeEvent) -> None:
        try:
            important = {"starting", "shutting_down", "idle", "error", "paused"}
            if event.new_state.value in important:
                await self._notifier._send(
                    f"\U0001f916 <b>Bot State</b>\n"
                    f"Strategy: <code>{event.strategy_id}</code>\n"
                    f"{event.old_state.value} → <b>{event.new_state.value}</b>\n"
                    f"Reason: {event.reason}"
                )
        except Exception:
            logger.exception("Failed to send state change alert")

    async def _on_regime_change(self, event: RegimeChangeEvent) -> None:
        try:
            old = event.old_regime.value if event.old_regime else "(none)"
            new_preset = event.overrides.get("new_preset", "?")
            await self._notifier._send(
                f"\U0001f504 <b>Regime Switch</b>\n"
                f"Strategy: <code>{event.strategy_id}</code>\n"
                f"Regime: {old} → <b>{event.new_regime.value}</b>\n"
                f"Preset: {new_preset}"
            )
        except Exception:
            logger.exception("Failed to send regime change alert")

    async def _on_stop_loss(self, event: StopLossTriggeredEvent) -> None:
        try:
            await self._notifier.send_risk_alert(
                strategy_id=event.strategy_id,
                alert_type="stop_loss_triggered",
                message=f"SL @ {event.stop_loss_price:,.0f} (trigger: {event.trigger_price:,.0f})",
            )
        except Exception:
            logger.exception("Failed to send stop loss alert")
