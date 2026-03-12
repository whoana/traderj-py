"""Risk engine with ATR-based dynamic risk management.

Key features:
  - Volatility-inverse position sizing (target_risk / ATR_pct)
  - ATR-based dynamic stop loss (entry - 2.0 * ATR)
  - Volatility cap (ATR > 8% blocks entry)
  - Cooldown after consecutive losses
  - Daily loss limit
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskConfig:
    """Risk parameters."""

    # Position sizing
    max_position_pct: float = 0.20
    min_position_pct: float = 0.05
    target_risk_pct: float = 0.02
    use_volatility_sizing: bool = True

    # Stop loss
    stop_loss_pct: float = 0.03
    atr_stop_multiplier: float = 2.0
    use_atr_stop: bool = True

    # Take profit (R:R ratio)
    reward_risk_ratio: float = 2.0
    use_take_profit: bool = True

    # Trailing stop
    trailing_stop_activation_pct: float = 0.01  # activate after 1% gain
    trailing_stop_distance_pct: float = 0.015   # trail at 1.5% from high

    # Volatility cap
    volatility_cap_pct: float = 0.08

    # Daily/consecutive limits
    daily_max_loss_pct: float = 0.05
    max_consecutive_losses: int = 3
    cooldown_hours: int = 24
    min_order_krw: float = 5_000.0
    fee_rate: float = 0.0005


@dataclass
class RiskDecision:
    """Risk evaluation result."""

    allowed: bool
    reason: str
    position_size_krw: float = 0.0
    position_pct: float = 0.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    trailing_stop_activation: float = 0.0
    trailing_stop_distance_pct: float = 0.0
    atr_pct: float = 0.0
    volatility_status: str = "normal"  # "normal" | "warning" | "blocked"


class RiskEngine:
    """ATR-based dynamic risk management engine.

    Improvements over legacy:
      1. ATR-based dynamic stop loss (fixed 3% -> entry - 2.0*ATR)
      2. Volatility-inverse position sizing (fixed 20% -> target_risk / ATR_pct)
      3. Volatility cap (ATR > 8% -> entry blocked)
      4. Cooldown after consecutive losses
    """

    def __init__(
        self,
        config: RiskConfig | None = None,
        strategy_id: str = "STR-001",
    ) -> None:
        self.config = config or RiskConfig()
        self.strategy_id = strategy_id

        # In-memory risk state (persisted externally via DataStore)
        self.consecutive_losses: int = 0
        self.daily_pnl: float = 0.0
        self.daily_date: str = ""
        self.cooldown_until: datetime | None = None

    def evaluate_buy(
        self,
        total_balance_krw: float,
        current_price: float,
        current_atr: float,
        existing_position_krw: float = 0.0,
    ) -> RiskDecision:
        """Evaluate whether a buy is allowed and compute position size/stop loss."""
        self._ensure_daily_reset()

        # 1. Cooldown check
        if self.cooldown_until and datetime.now(UTC) < self.cooldown_until:
            remaining = (self.cooldown_until - datetime.now(UTC)).total_seconds() / 3600
            return RiskDecision(
                allowed=False, reason=f"cooldown_active_{remaining:.1f}h"
            )

        # 2. Daily loss limit
        if total_balance_krw > 0:
            daily_loss_pct = abs(min(0, self.daily_pnl)) / total_balance_krw
            if daily_loss_pct >= self.config.daily_max_loss_pct:
                return RiskDecision(
                    allowed=False,
                    reason=f"daily_loss_limit_{daily_loss_pct:.1%}",
                )

        # 3. Volatility cap
        atr_pct = current_atr / current_price if current_price > 0 else 0
        vol_status = "normal"
        if atr_pct > self.config.volatility_cap_pct:
            return RiskDecision(
                allowed=False,
                reason=f"volatility_cap_{atr_pct:.1%}",
                atr_pct=atr_pct,
                volatility_status="blocked",
            )
        elif atr_pct > self.config.volatility_cap_pct * 0.75:
            vol_status = "warning"

        # 4. Position sizing
        if self.config.use_volatility_sizing and atr_pct > 0:
            position_pct = self.config.target_risk_pct / atr_pct
            position_pct = max(
                self.config.min_position_pct,
                min(self.config.max_position_pct, position_pct),
            )
        else:
            position_pct = self.config.max_position_pct

        available_krw = total_balance_krw - existing_position_krw
        position_size_krw = available_krw * position_pct

        if position_size_krw < self.config.min_order_krw:
            return RiskDecision(
                allowed=False,
                reason="below_min_order",
                position_size_krw=position_size_krw,
            )

        # 5. Stop loss calculation
        if self.config.use_atr_stop and current_atr > 0:
            stop_loss = current_price - (current_atr * self.config.atr_stop_multiplier)
        else:
            stop_loss = current_price * (1 - self.config.stop_loss_pct)

        stop_loss = max(0, stop_loss)

        # 6. Take profit calculation (R:R ratio)
        risk_amount = current_price - stop_loss
        if self.config.use_take_profit and risk_amount > 0:
            take_profit = current_price + (risk_amount * self.config.reward_risk_ratio)
        else:
            take_profit = 0.0

        # 7. Trailing stop parameters
        trailing_activation = current_price * (1 + self.config.trailing_stop_activation_pct)

        return RiskDecision(
            allowed=True,
            reason="approved",
            position_size_krw=round(position_size_krw, 0),
            position_pct=round(position_pct, 4),
            stop_loss_price=round(stop_loss, 0),
            take_profit_price=round(take_profit, 0),
            trailing_stop_activation=round(trailing_activation, 0),
            trailing_stop_distance_pct=self.config.trailing_stop_distance_pct,
            atr_pct=round(atr_pct, 6),
            volatility_status=vol_status,
        )

    def record_trade_result(self, pnl: float) -> None:
        """Record trade result and update risk state."""
        self._ensure_daily_reset()
        self.daily_pnl += pnl

        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.config.max_consecutive_losses:
                self.cooldown_until = datetime.now(UTC) + timedelta(
                    hours=self.config.cooldown_hours
                )
                logger.warning(
                    "Cooldown activated: %d consecutive losses",
                    self.consecutive_losses,
                )
        else:
            self.consecutive_losses = 0

    def _ensure_daily_reset(self) -> None:
        """Reset daily PnL if date changed."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self.daily_date != today:
            self.daily_pnl = 0.0
            self.daily_date = today
