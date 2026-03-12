"""Position Manager — open/close positions, track unrealized PnL.

Subscribes to:
- OrderFilledEvent → open/close positions
- MarketTickEvent → update unrealized PnL

Publishes:
- PositionOpenedEvent
- PositionClosedEvent
- StopLossTriggeredEvent
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

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

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages position lifecycle and real-time PnL tracking."""

    def __init__(
        self,
        data_store: object,
        event_bus: object,
    ) -> None:
        self._store = data_store
        self._bus = event_bus
        self._positions: dict[str, Position] = {}  # strategy_id → Position (1 per strategy)
        # Trailing stop state per strategy: {strategy_id: {highest_price, activation_price, distance_pct}}
        self._trailing_state: dict[str, dict] = {}

    @property
    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    async def load_open_positions(self) -> None:
        """Load open positions from DB on startup."""
        positions = await self._store.get_positions(status="open")
        for pos in positions:
            self._positions[pos.strategy_id] = pos
        logger.info("Loaded %d open positions", len(positions))

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        """Handle filled order — open or close position."""
        if event.side == OrderSide.BUY:
            await self._open_position(event)
        else:
            await self._close_position(event)

    async def on_market_tick(self, event: MarketTickEvent) -> None:
        """Update unrealized PnL, trailing stop, and check SL/TP for all open positions."""
        for strategy_id, pos in list(self._positions.items()):
            if pos.symbol != event.symbol:
                continue

            new_price = event.price
            pnl = self._calc_unrealized_pnl(pos, new_price)

            # Update trailing stop if applicable
            new_trailing = pos.trailing_stop
            if strategy_id in self._trailing_state:
                new_trailing = await self._update_trailing_stop(
                    strategy_id, pos, new_price
                )

            updated = Position(
                id=pos.id,
                strategy_id=pos.strategy_id,
                symbol=pos.symbol,
                side=pos.side,
                amount=pos.amount,
                entry_price=pos.entry_price,
                current_price=new_price,
                stop_loss=pos.stop_loss,
                trailing_stop=new_trailing,
                unrealized_pnl=pnl,
                realized_pnl=pos.realized_pnl,
                status=pos.status,
                opened_at=pos.opened_at,
                closed_at=pos.closed_at,
                take_profit=pos.take_profit,
            )
            self._positions[strategy_id] = updated
            await self._store.save_position(updated)

            # Check take profit first (higher priority)
            if pos.take_profit is not None and self._is_tp_triggered(pos, new_price):
                await self._trigger_take_profit(updated, new_price)
                continue

            # Check trailing stop (overrides fixed stop loss)
            if new_trailing is not None and self._is_stop_triggered_at(
                pos.side, new_price, new_trailing
            ):
                await self._trigger_stop_loss(updated, new_price)
                continue

            # Check fixed stop loss
            if pos.stop_loss is not None and self._is_stop_triggered(pos, new_price):
                await self._trigger_stop_loss(updated, new_price)

    def get_position(self, strategy_id: str) -> Position | None:
        return self._positions.get(strategy_id)

    def has_open_position(self, strategy_id: str) -> bool:
        return strategy_id in self._positions

    def configure_trailing_stop(
        self,
        strategy_id: str,
        activation_price: Decimal,
        distance_pct: float,
    ) -> bool:
        """Configure trailing stop for a position.

        Args:
            activation_price: Price at which trailing stop activates.
            distance_pct: Distance from highest price as a percentage (e.g., 0.015 = 1.5%).
        """
        if strategy_id not in self._positions:
            return False
        pos = self._positions[strategy_id]
        self._trailing_state[strategy_id] = {
            "activation_price": activation_price,
            "distance_pct": distance_pct,
            "highest_price": pos.entry_price,
            "activated": False,
        }
        logger.info(
            "Trailing stop configured for %s: activation=%s, distance=%.2f%%",
            strategy_id,
            activation_price,
            distance_pct * 100,
        )
        return True

    def set_take_profit(self, strategy_id: str, take_profit: Decimal) -> bool:
        """Set take-profit target for an open position."""
        pos = self._positions.get(strategy_id)
        if pos is None:
            return False

        updated = Position(
            id=pos.id,
            strategy_id=pos.strategy_id,
            symbol=pos.symbol,
            side=pos.side,
            amount=pos.amount,
            entry_price=pos.entry_price,
            current_price=pos.current_price,
            stop_loss=pos.stop_loss,
            trailing_stop=pos.trailing_stop,
            unrealized_pnl=pos.unrealized_pnl,
            realized_pnl=pos.realized_pnl,
            status=pos.status,
            opened_at=pos.opened_at,
            closed_at=pos.closed_at,
            take_profit=take_profit,
        )
        self._positions[strategy_id] = updated
        return True

    # ── Internal ─────────────────────────────────────────────────────

    async def _update_trailing_stop(
        self,
        strategy_id: str,
        pos: Position,
        current_price: Decimal,
    ) -> Decimal | None:
        """Update trailing stop based on price movement. Returns new trailing stop price."""
        state = self._trailing_state.get(strategy_id)
        if state is None:
            return pos.trailing_stop

        activation_price = state["activation_price"]
        distance_pct = Decimal(str(state["distance_pct"]))
        highest = state["highest_price"]

        # Check if trailing stop should activate
        if not state["activated"]:
            if pos.side == OrderSide.BUY and current_price >= activation_price:
                state["activated"] = True
                state["highest_price"] = current_price
                logger.info(
                    "Trailing stop activated for %s at %s",
                    strategy_id,
                    current_price,
                )
            else:
                return pos.trailing_stop

        # Update highest price and trailing stop
        if pos.side == OrderSide.BUY and current_price > highest:
            old_stop = pos.trailing_stop
            state["highest_price"] = current_price
            new_stop = current_price * (1 - distance_pct)

            if old_stop is None or new_stop > old_stop:
                await self._bus.publish(
                    TrailingStopUpdatedEvent(
                        position_id=pos.id,
                        strategy_id=strategy_id,
                        old_stop=old_stop or Decimal("0"),
                        new_stop=new_stop,
                        current_price=current_price,
                    )
                )
                logger.debug(
                    "Trailing stop updated for %s: %s -> %s (high=%s)",
                    strategy_id,
                    old_stop,
                    new_stop,
                    current_price,
                )
                return new_stop

        return pos.trailing_stop

    async def _open_position(self, event: OrderFilledEvent) -> None:
        """Open a new position from a BUY fill."""
        if event.strategy_id in self._positions:
            logger.warning(
                "Strategy %s already has open position, skipping open",
                event.strategy_id,
            )
            return

        pos_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        position = Position(
            id=pos_id,
            strategy_id=event.strategy_id,
            symbol=event.symbol,
            side=OrderSide.BUY,
            amount=event.amount,
            entry_price=event.actual_price,
            current_price=event.actual_price,
            stop_loss=None,
            trailing_stop=None,
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            status=PositionStatus.OPEN,
            opened_at=now,
        )

        self._positions[event.strategy_id] = position
        await self._store.save_position(position)

        await self._bus.publish(
            PositionOpenedEvent(
                position_id=pos_id,
                strategy_id=event.strategy_id,
                symbol=event.symbol,
                entry_price=event.actual_price,
                amount=event.amount,
            )
        )
        logger.info(
            "Opened position %s for %s at %s",
            pos_id,
            event.strategy_id,
            event.actual_price,
        )

    async def _close_position(
        self, event: OrderFilledEvent, exit_reason: str = "sell_signal"
    ) -> None:
        """Close existing position from a SELL fill."""
        pos = self._positions.get(event.strategy_id)
        if pos is None:
            logger.warning(
                "No open position for %s to close", event.strategy_id
            )
            return

        realized = self._calc_realized_pnl(pos, event.actual_price)
        now = datetime.now(timezone.utc)

        closed_pos = Position(
            id=pos.id,
            strategy_id=pos.strategy_id,
            symbol=pos.symbol,
            side=pos.side,
            amount=pos.amount,
            entry_price=pos.entry_price,
            current_price=event.actual_price,
            stop_loss=pos.stop_loss,
            trailing_stop=pos.trailing_stop,
            unrealized_pnl=Decimal("0"),
            realized_pnl=realized,
            status=PositionStatus.CLOSED,
            opened_at=pos.opened_at,
            closed_at=now,
            take_profit=pos.take_profit,
        )

        del self._positions[event.strategy_id]
        self._trailing_state.pop(event.strategy_id, None)
        await self._store.save_position(closed_pos)

        await self._bus.publish(
            PositionClosedEvent(
                position_id=pos.id,
                strategy_id=event.strategy_id,
                symbol=event.symbol,
                realized_pnl=realized,
                exit_reason=exit_reason,
            )
        )
        logger.info(
            "Closed position %s for %s, PnL=%s, reason=%s",
            pos.id,
            event.strategy_id,
            realized,
            exit_reason,
        )

    async def _trigger_stop_loss(
        self, pos: Position, trigger_price: Decimal
    ) -> None:
        """Publish stop loss event."""
        # Determine which stop was triggered (trailing or fixed)
        effective_stop = pos.trailing_stop if pos.trailing_stop is not None else pos.stop_loss
        await self._bus.publish(
            StopLossTriggeredEvent(
                position_id=pos.id,
                strategy_id=pos.strategy_id,
                trigger_price=trigger_price,
                stop_loss_price=effective_stop,  # type: ignore[arg-type]
            )
        )
        logger.warning(
            "Stop loss triggered for %s at %s (stop=%s, trailing=%s)",
            pos.strategy_id,
            trigger_price,
            pos.stop_loss,
            pos.trailing_stop,
        )

    async def _trigger_take_profit(
        self, pos: Position, trigger_price: Decimal
    ) -> None:
        """Publish take profit event."""
        await self._bus.publish(
            TakeProfitTriggeredEvent(
                position_id=pos.id,
                strategy_id=pos.strategy_id,
                trigger_price=trigger_price,
                take_profit_price=pos.take_profit,  # type: ignore[arg-type]
            )
        )
        logger.info(
            "Take profit triggered for %s at %s (target=%s)",
            pos.strategy_id,
            trigger_price,
            pos.take_profit,
        )

    def set_stop_loss(self, strategy_id: str, stop_loss: Decimal) -> bool:
        """Update stop loss for an open position."""
        pos = self._positions.get(strategy_id)
        if pos is None:
            return False

        updated = Position(
            id=pos.id,
            strategy_id=pos.strategy_id,
            symbol=pos.symbol,
            side=pos.side,
            amount=pos.amount,
            entry_price=pos.entry_price,
            current_price=pos.current_price,
            stop_loss=stop_loss,
            trailing_stop=pos.trailing_stop,
            unrealized_pnl=pos.unrealized_pnl,
            realized_pnl=pos.realized_pnl,
            status=pos.status,
            opened_at=pos.opened_at,
            closed_at=pos.closed_at,
            take_profit=pos.take_profit,
        )
        self._positions[strategy_id] = updated
        return True

    @staticmethod
    def _calc_unrealized_pnl(pos: Position, current_price: Decimal) -> Decimal:
        """PnL = (current - entry) × amount for BUY side."""
        if pos.side == OrderSide.BUY:
            return (current_price - pos.entry_price) * pos.amount
        return (pos.entry_price - current_price) * pos.amount

    @staticmethod
    def _calc_realized_pnl(pos: Position, exit_price: Decimal) -> Decimal:
        if pos.side == OrderSide.BUY:
            return (exit_price - pos.entry_price) * pos.amount
        return (pos.entry_price - exit_price) * pos.amount

    @staticmethod
    def _is_stop_triggered(pos: Position, price: Decimal) -> bool:
        if pos.stop_loss is None:
            return False
        if pos.side == OrderSide.BUY:
            return price <= pos.stop_loss
        return price >= pos.stop_loss

    @staticmethod
    def _is_stop_triggered_at(
        side: OrderSide, price: Decimal, stop_price: Decimal
    ) -> bool:
        """Check if price has breached a specific stop price."""
        if side == OrderSide.BUY:
            return price <= stop_price
        return price >= stop_price

    @staticmethod
    def _is_tp_triggered(pos: Position, price: Decimal) -> bool:
        """Check if take-profit target has been reached."""
        if pos.take_profit is None:
            return False
        if pos.side == OrderSide.BUY:
            return price >= pos.take_profit
        return price <= pos.take_profit
