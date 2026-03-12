"""Bot StateMachine — 9-state lifecycle with DB persistence.

States: IDLE → STARTING → SCANNING → VALIDATING → EXECUTING →
        LOGGING → MONITORING → PAUSED → SHUTTING_DOWN

Valid transitions defined in TRANSITIONS map.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from shared.enums import BotStateEnum, TradingMode
from shared.events import BotStateChangeEvent
from shared.models import BotStateModel

logger = logging.getLogger(__name__)

# Valid state transitions
TRANSITIONS: dict[BotStateEnum, set[BotStateEnum]] = {
    BotStateEnum.IDLE: {BotStateEnum.STARTING},
    BotStateEnum.STARTING: {BotStateEnum.SCANNING, BotStateEnum.SHUTTING_DOWN},
    BotStateEnum.SCANNING: {BotStateEnum.VALIDATING, BotStateEnum.PAUSED, BotStateEnum.SHUTTING_DOWN},
    BotStateEnum.VALIDATING: {BotStateEnum.EXECUTING, BotStateEnum.SCANNING, BotStateEnum.SHUTTING_DOWN},
    BotStateEnum.EXECUTING: {BotStateEnum.LOGGING, BotStateEnum.SHUTTING_DOWN},
    BotStateEnum.LOGGING: {BotStateEnum.MONITORING, BotStateEnum.SHUTTING_DOWN},
    BotStateEnum.MONITORING: {BotStateEnum.SCANNING, BotStateEnum.PAUSED, BotStateEnum.SHUTTING_DOWN},
    BotStateEnum.PAUSED: {BotStateEnum.SCANNING, BotStateEnum.SHUTTING_DOWN},
    BotStateEnum.SHUTTING_DOWN: {BotStateEnum.IDLE},
}

# States considered active (bot is running)
ACTIVE_STATES = {
    BotStateEnum.SCANNING,
    BotStateEnum.VALIDATING,
    BotStateEnum.EXECUTING,
    BotStateEnum.LOGGING,
    BotStateEnum.MONITORING,
}


class InvalidTransitionError(Exception):
    def __init__(self, current: BotStateEnum, target: BotStateEnum) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Invalid transition: {current} → {target}")


class StateMachine:
    """Bot state machine with DB persistence and EventBus integration."""

    def __init__(
        self,
        strategy_id: str,
        trading_mode: TradingMode,
        data_store: object,
        event_bus: object,
    ) -> None:
        self._strategy_id = strategy_id
        self._trading_mode = trading_mode
        self._store = data_store
        self._bus = event_bus
        self._state = BotStateEnum.IDLE

    @property
    def state(self) -> BotStateEnum:
        return self._state

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def is_active(self) -> bool:
        return self._state in ACTIVE_STATES

    @property
    def is_idle(self) -> bool:
        return self._state == BotStateEnum.IDLE

    async def load_state(self) -> BotStateEnum:
        """Load persisted state from DB. Returns loaded or default state."""
        model = await self._store.get_bot_state(self._strategy_id)
        if model is not None:
            self._state = model.state
            logger.info("Loaded state %s for %s", self._state, self._strategy_id)
        return self._state

    async def transition(self, target: BotStateEnum, reason: str = "") -> None:
        """Transition to a new state. Raises InvalidTransitionError if invalid."""
        allowed = TRANSITIONS.get(self._state, set())
        if target not in allowed:
            raise InvalidTransitionError(self._state, target)

        old = self._state
        self._state = target
        await self._persist()
        await self._publish(old, target, reason)

        logger.info(
            "State %s → %s for %s (%s)",
            old,
            target,
            self._strategy_id,
            reason or "no reason",
        )

    async def force_state(self, target: BotStateEnum, reason: str = "") -> None:
        """Force state without transition validation. For recovery only."""
        old = self._state
        self._state = target
        await self._persist()
        await self._publish(old, target, f"FORCE: {reason}")

        logger.warning(
            "FORCED state %s → %s for %s (%s)",
            old,
            target,
            self._strategy_id,
            reason,
        )

    async def _persist(self) -> None:
        model = BotStateModel(
            strategy_id=self._strategy_id,
            state=self._state,
            trading_mode=self._trading_mode,
            last_updated=datetime.now(timezone.utc),
        )
        await self._store.save_bot_state(model)

    async def _publish(
        self, old: BotStateEnum, new: BotStateEnum, reason: str
    ) -> None:
        event = BotStateChangeEvent(
            strategy_id=self._strategy_id,
            old_state=old,
            new_state=new,
            reason=reason,
        )
        await self._bus.publish(event)
