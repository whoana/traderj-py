"""DCA (Dollar-Cost Averaging) strategy engine.

Periodic fixed-amount buying with RSI-based dynamic sizing:
  - Base: Buy fixed KRW amount at regular intervals
  - RSI Enhancement: Increase buy amount when RSI < 30 (oversold),
    decrease when RSI > 70 (overbought), skip when RSI > 80
  - ATR Guard: Skip buy when ATR > volatility cap
  - Max Position: Don't exceed max allocation percentage
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DCAConfig:
    """DCA strategy parameters."""

    # Base buy amount
    base_buy_krw: float = 100_000.0
    min_buy_krw: float = 5_000.0

    # Schedule
    interval_hours: int = 24  # buy every N hours

    # RSI-based dynamic sizing
    use_rsi_scaling: bool = True
    rsi_oversold: float = 30.0    # scale up below this
    rsi_overbought: float = 70.0  # scale down above this
    rsi_skip: float = 80.0        # skip buy above this
    rsi_scale_up: float = 1.5     # multiplier when oversold
    rsi_scale_down: float = 0.5   # multiplier when overbought

    # Safety limits
    max_position_pct: float = 0.50  # max % of total balance in position
    volatility_cap_pct: float = 0.08  # skip if ATR% > this


@dataclass
class DCADecision:
    """DCA evaluation result."""

    should_buy: bool
    reason: str
    buy_amount_krw: float = 0.0
    rsi_adjustment: str = "none"  # "scale_up" | "scale_down" | "skip" | "none"
    next_buy_after: datetime | None = None


class DCAEngine:
    """DCA strategy engine with RSI-based dynamic sizing."""

    def __init__(
        self,
        config: DCAConfig | None = None,
        strategy_id: str = "DCA-001",
    ) -> None:
        self.config = config or DCAConfig()
        self.strategy_id = strategy_id
        self._last_buy_time: datetime | None = None
        self._total_invested: float = 0.0
        self._buy_count: int = 0

    @property
    def buy_count(self) -> int:
        return self._buy_count

    @property
    def total_invested(self) -> float:
        return self._total_invested

    def evaluate(
        self,
        total_balance_krw: float,
        existing_position_krw: float,
        current_rsi: float | None = None,
        current_atr_pct: float | None = None,
        now: datetime | None = None,
    ) -> DCADecision:
        """Evaluate whether to execute a DCA buy.

        Args:
            total_balance_krw: Total portfolio value in KRW.
            existing_position_krw: Current position value in KRW.
            current_rsi: Current RSI value (14-period).
            current_atr_pct: Current ATR as percentage of price.
            now: Current timestamp.

        Returns:
            DCADecision with buy amount and reasoning.
        """
        now = now or datetime.now(UTC)

        # 1. Interval check
        if self._last_buy_time is not None:
            next_buy = self._last_buy_time + timedelta(hours=self.config.interval_hours)
            if now < next_buy:
                return DCADecision(
                    should_buy=False,
                    reason="interval_not_reached",
                    next_buy_after=next_buy,
                )

        # 2. Volatility cap
        if current_atr_pct is not None and current_atr_pct > self.config.volatility_cap_pct:
            return DCADecision(
                should_buy=False,
                reason=f"volatility_cap_{current_atr_pct:.1%}",
            )

        # 3. Max position check
        if total_balance_krw > 0:
            position_pct = existing_position_krw / total_balance_krw
            if position_pct >= self.config.max_position_pct:
                return DCADecision(
                    should_buy=False,
                    reason=f"max_position_{position_pct:.1%}",
                )

        # 4. RSI-based amount adjustment
        buy_amount = self.config.base_buy_krw
        rsi_adj = "none"

        if self.config.use_rsi_scaling and current_rsi is not None:
            if current_rsi >= self.config.rsi_skip:
                return DCADecision(
                    should_buy=False,
                    reason=f"rsi_too_high_{current_rsi:.0f}",
                    rsi_adjustment="skip",
                )
            elif current_rsi >= self.config.rsi_overbought:
                buy_amount *= self.config.rsi_scale_down
                rsi_adj = "scale_down"
            elif current_rsi <= self.config.rsi_oversold:
                buy_amount *= self.config.rsi_scale_up
                rsi_adj = "scale_up"

        # 5. Ensure within available balance
        available_krw = total_balance_krw - existing_position_krw
        buy_amount = min(buy_amount, available_krw)

        if buy_amount < self.config.min_buy_krw:
            return DCADecision(
                should_buy=False,
                reason="below_min_buy",
                buy_amount_krw=buy_amount,
            )

        return DCADecision(
            should_buy=True,
            reason="dca_buy_approved",
            buy_amount_krw=round(buy_amount, 0),
            rsi_adjustment=rsi_adj,
        )

    def record_buy(self, amount_krw: float, now: datetime | None = None) -> None:
        """Record a completed DCA buy."""
        self._last_buy_time = now or datetime.now(UTC)
        self._total_invested += amount_krw
        self._buy_count += 1
        logger.info(
            "DCA buy #%d recorded: %s KRW (total: %s KRW)",
            self._buy_count,
            amount_krw,
            self._total_invested,
        )

    def reset(self) -> None:
        """Reset DCA state."""
        self._last_buy_time = None
        self._total_invested = 0.0
        self._buy_count = 0
