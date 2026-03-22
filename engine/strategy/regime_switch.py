"""Automatic strategy switching based on market regime detection.

Monitors regime changes and recommends/applies preset transitions:
  - Debounce: requires N consecutive detections of the same regime before switching
  - Cooldown: minimum time between switches to prevent whipsawing
  - Override: allows manual lock to prevent auto-switching
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from engine.strategy.dca import DCAConfig
from engine.strategy.grid import GridConfig
from engine.strategy.presets import STRATEGY_PRESETS, StrategyPreset
from engine.strategy.regime import (
    REGIME_PRESET_MAP,
    RegimeConfig,
    RegimeResult,
)
from engine.strategy.regime_config import (
    DCA_REGIME_MAP,
    GRID_REGIME_MAP,
    build_grid_config,
)
from shared.enums import RegimeType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegimeSwitchConfig:
    """Auto-switch parameters."""

    debounce_count: int = 3          # consecutive detections before switch
    cooldown_minutes: int = 60       # min time between switches
    enabled: bool = True
    regime_config: RegimeConfig = RegimeConfig()

    # Position handling on regime switch
    close_position_on_switch: bool = True     # enable hybrid close logic
    loss_threshold_pct: float = 0.015         # if unrealized loss > 1.5%, tighten SL instead
    tightened_sl_pct: float = 0.015           # tightened SL distance from entry price
    tightened_sl_min_distance_pct: float = 0.005  # min SL distance from current price


@dataclass
class SwitchDecision:
    """Result of regime switch evaluation."""

    should_switch: bool
    reason: str
    current_regime: RegimeType | None = None
    recommended_preset: str = ""
    confidence: float = 0.0
    consecutive_detections: int = 0


class RegimeSwitchManager:
    """Manages automatic strategy switching based on regime detection."""

    def __init__(
        self,
        config: RegimeSwitchConfig | None = None,
        preset_map: dict[RegimeType, str] | None = None,
    ) -> None:
        self.config = config or RegimeSwitchConfig()
        self._preset_map = preset_map or dict(REGIME_PRESET_MAP)

        self._current_regime: RegimeType | None = None
        self._current_preset: str = ""
        self._pending_regime: RegimeType | None = None
        self._pending_count: int = 0
        self._last_switch_time: datetime | None = None
        self._locked: bool = False
        self._switch_history: list[dict] = []

    @property
    def current_regime(self) -> RegimeType | None:
        return self._current_regime

    @property
    def current_preset(self) -> str:
        return self._current_preset

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def switch_count(self) -> int:
        return len(self._switch_history)

    def lock(self) -> None:
        """Lock to prevent auto-switching."""
        self._locked = True
        logger.info("Regime switch locked")

    def unlock(self) -> None:
        """Unlock to allow auto-switching."""
        self._locked = False
        logger.info("Regime switch unlocked")

    def set_initial_preset(self, preset_id: str) -> None:
        """Set the initial active preset (no switch event)."""
        self._current_preset = preset_id

    def evaluate(
        self,
        regime_result: RegimeResult,
        now: datetime | None = None,
    ) -> SwitchDecision:
        """Evaluate whether a strategy switch is needed.

        Args:
            regime_result: Current regime detection result.
            now: Current timestamp.

        Returns:
            SwitchDecision with recommendation.
        """
        now = now or datetime.now(UTC)
        detected = regime_result.regime

        # Not enabled
        if not self.config.enabled:
            return SwitchDecision(
                should_switch=False,
                reason="auto_switch_disabled",
                current_regime=self._current_regime,
            )

        # Locked
        if self._locked:
            return SwitchDecision(
                should_switch=False,
                reason="manually_locked",
                current_regime=self._current_regime,
            )

        # Same as current → no action
        if detected == self._current_regime:
            self._pending_regime = None
            self._pending_count = 0
            return SwitchDecision(
                should_switch=False,
                reason="same_regime",
                current_regime=self._current_regime,
            )

        # Cooldown check
        if self._last_switch_time is not None:
            elapsed = (now - self._last_switch_time).total_seconds() / 60
            if elapsed < self.config.cooldown_minutes:
                return SwitchDecision(
                    should_switch=False,
                    reason=f"cooldown_{self.config.cooldown_minutes - elapsed:.0f}min",
                    current_regime=self._current_regime,
                )

        # Debounce: track consecutive detections
        if detected == self._pending_regime:
            self._pending_count += 1
        else:
            self._pending_regime = detected
            self._pending_count = 1

        recommended = self._preset_map.get(detected, "")

        if self._pending_count < self.config.debounce_count:
            return SwitchDecision(
                should_switch=False,
                reason=f"debounce_{self._pending_count}/{self.config.debounce_count}",
                current_regime=self._current_regime,
                recommended_preset=recommended,
                confidence=regime_result.confidence,
                consecutive_detections=self._pending_count,
            )

        # Switch approved
        return SwitchDecision(
            should_switch=True,
            reason="regime_change_confirmed",
            current_regime=detected,
            recommended_preset=recommended,
            confidence=regime_result.confidence,
            consecutive_detections=self._pending_count,
        )

    def apply_switch(self, decision: SwitchDecision, now: datetime | None = None) -> str:
        """Apply a switch decision. Returns the new preset ID.

        Should only be called when decision.should_switch is True.
        """
        now = now or datetime.now(UTC)
        old_regime = self._current_regime
        old_preset = self._current_preset

        self._current_regime = decision.current_regime
        self._current_preset = decision.recommended_preset
        self._last_switch_time = now
        self._pending_regime = None
        self._pending_count = 0

        self._switch_history.append({
            "time": now.isoformat(),
            "old_regime": old_regime.value if old_regime else None,
            "new_regime": decision.current_regime.value if decision.current_regime else None,
            "old_preset": old_preset,
            "new_preset": decision.recommended_preset,
            "confidence": decision.confidence,
        })

        logger.info(
            "Strategy switched: %s → %s (regime: %s → %s, confidence=%.2f)",
            old_preset,
            decision.recommended_preset,
            old_regime,
            decision.current_regime,
            decision.confidence,
        )

        return decision.recommended_preset

    def get_preset(self, preset_id: str) -> StrategyPreset | None:
        """Look up a strategy preset by ID."""
        return STRATEGY_PRESETS.get(preset_id)

    def get_dca_config(self, regime: RegimeType | None = None) -> DCAConfig | None:
        """Get DCA config for the given or current regime."""
        regime = regime or self._current_regime
        if regime is None:
            return None
        preset = DCA_REGIME_MAP.get(regime)
        return preset.config if preset else None

    def get_grid_config(
        self,
        current_price: float,
        regime: RegimeType | None = None,
    ) -> GridConfig | None:
        """Get GridConfig for the given or current regime.

        Returns None if grid is disabled for this regime or price is invalid.
        """
        regime = regime or self._current_regime
        if regime is None:
            return None
        preset = GRID_REGIME_MAP.get(regime)
        if preset is None:
            return None
        return build_grid_config(preset, current_price)

    def get_history(self) -> list[dict]:
        """Return switch history."""
        return list(self._switch_history)
