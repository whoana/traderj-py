"""Grid Trading strategy engine.

Places buy/sell orders at fixed price intervals within a range:
  - Divides a price range into N grid levels
  - Buy at each level when price drops to it
  - Sell at the level above when price rises to it
  - Profits from price oscillation in sideways markets

Grid types:
  - ARITHMETIC: Equal price spacing (upper - lower) / N
  - GEOMETRIC: Equal percentage spacing (upper / lower)^(1/N)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

logger = logging.getLogger(__name__)


class GridType(StrEnum):
    ARITHMETIC = "arithmetic"
    GEOMETRIC = "geometric"


class GridLevelStatus(StrEnum):
    PENDING_BUY = "pending_buy"
    FILLED_BUY = "filled_buy"
    PENDING_SELL = "pending_sell"
    FILLED_SELL = "filled_sell"


@dataclass(frozen=True)
class GridConfig:
    """Grid strategy parameters."""

    upper_price: float = 0.0   # top of grid range
    lower_price: float = 0.0   # bottom of grid range
    num_grids: int = 10        # number of grid levels
    grid_type: GridType = GridType.ARITHMETIC
    investment_per_grid: float = 100_000.0  # KRW per grid level
    min_order_krw: float = 5_000.0
    max_total_investment: float = 2_000_000.0  # total budget


@dataclass
class GridLevel:
    """A single grid level."""

    index: int
    buy_price: float
    sell_price: float
    status: GridLevelStatus = GridLevelStatus.PENDING_BUY
    filled_amount: float = 0.0
    filled_price: float = 0.0


@dataclass
class GridAction:
    """Grid engine recommended action."""

    should_act: bool
    action: str = "none"  # "buy" | "sell" | "none"
    price: float = 0.0
    amount_krw: float = 0.0
    grid_index: int = -1
    reason: str = ""


class GridEngine:
    """Grid trading engine — manages grid levels and generates buy/sell actions."""

    def __init__(
        self,
        config: GridConfig,
        strategy_id: str = "GRID-001",
    ) -> None:
        if config.upper_price <= config.lower_price:
            raise ValueError("upper_price must be greater than lower_price")
        if config.num_grids < 2:
            raise ValueError("num_grids must be at least 2")

        self.config = config
        self.strategy_id = strategy_id
        self._levels: list[GridLevel] = []
        self._total_invested: float = 0.0
        self._total_profit: float = 0.0
        self._build_grid()

    @property
    def levels(self) -> list[GridLevel]:
        return list(self._levels)

    @property
    def total_invested(self) -> float:
        return self._total_invested

    @property
    def total_profit(self) -> float:
        return self._total_profit

    @property
    def active_levels(self) -> int:
        """Count of levels with filled buys waiting to sell."""
        return sum(
            1 for lv in self._levels if lv.status == GridLevelStatus.FILLED_BUY
        )

    def evaluate(self, current_price: float) -> list[GridAction]:
        """Evaluate current price against grid levels.

        Returns a list of actions (may be multiple if price jumped across levels).
        """
        if current_price <= 0:
            return []

        actions: list[GridAction] = []

        for level in self._levels:
            if level.status == GridLevelStatus.PENDING_BUY:
                if current_price <= level.buy_price:
                    if self._can_invest():
                        actions.append(GridAction(
                            should_act=True,
                            action="buy",
                            price=level.buy_price,
                            amount_krw=self.config.investment_per_grid,
                            grid_index=level.index,
                            reason=f"grid_buy_level_{level.index}",
                        ))

            elif level.status == GridLevelStatus.FILLED_BUY:
                if current_price >= level.sell_price:
                    actions.append(GridAction(
                        should_act=True,
                        action="sell",
                        price=level.sell_price,
                        amount_krw=level.filled_amount * level.sell_price,
                        grid_index=level.index,
                        reason=f"grid_sell_level_{level.index}",
                    ))

        return actions

    def record_fill(
        self,
        grid_index: int,
        action: str,
        filled_price: float,
        filled_amount: float,
    ) -> None:
        """Record a grid order fill."""
        if grid_index < 0 or grid_index >= len(self._levels):
            logger.warning("Invalid grid index: %d", grid_index)
            return

        level = self._levels[grid_index]

        if action == "buy":
            level.status = GridLevelStatus.FILLED_BUY
            level.filled_price = filled_price
            level.filled_amount = filled_amount
            self._total_invested += filled_price * filled_amount
            logger.info(
                "Grid buy filled: level=%d, price=%s, amount=%s",
                grid_index, filled_price, filled_amount,
            )

        elif action == "sell":
            profit = (filled_price - level.filled_price) * filled_amount
            self._total_profit += profit
            level.status = GridLevelStatus.PENDING_BUY  # reset for next cycle
            level.filled_amount = 0.0
            level.filled_price = 0.0
            self._total_invested -= filled_price * filled_amount
            logger.info(
                "Grid sell filled: level=%d, price=%s, profit=%s",
                grid_index, filled_price, profit,
            )

    def get_summary(self) -> dict:
        """Get grid status summary."""
        pending_buy = sum(1 for lv in self._levels if lv.status == GridLevelStatus.PENDING_BUY)
        filled_buy = sum(1 for lv in self._levels if lv.status == GridLevelStatus.FILLED_BUY)
        return {
            "strategy_id": self.strategy_id,
            "grid_type": self.config.grid_type,
            "num_grids": self.config.num_grids,
            "upper_price": self.config.upper_price,
            "lower_price": self.config.lower_price,
            "pending_buy": pending_buy,
            "filled_buy": filled_buy,
            "total_invested": round(self._total_invested, 0),
            "total_profit": round(self._total_profit, 0),
            "grid_spacing": self._calc_spacing(),
        }

    # ── Internal ─────────────────────────────────────────────────────

    def _build_grid(self) -> None:
        """Build grid levels based on config."""
        self._levels = []
        prices = self._calc_prices()

        for i in range(len(prices) - 1):
            level = GridLevel(
                index=i,
                buy_price=prices[i],
                sell_price=prices[i + 1],
            )
            self._levels.append(level)

    def _calc_prices(self) -> list[float]:
        """Calculate grid price levels from bottom to top."""
        n = self.config.num_grids
        lower = self.config.lower_price
        upper = self.config.upper_price

        if self.config.grid_type == GridType.ARITHMETIC:
            step = (upper - lower) / n
            return [round(lower + step * i, 0) for i in range(n + 1)]
        else:
            # Geometric: equal percentage spacing
            ratio = (upper / lower) ** (1 / n)
            return [round(lower * (ratio ** i), 0) for i in range(n + 1)]

    def _calc_spacing(self) -> float:
        """Calculate spacing between grid levels."""
        if self.config.grid_type == GridType.ARITHMETIC:
            return round(
                (self.config.upper_price - self.config.lower_price)
                / self.config.num_grids,
                0,
            )
        else:
            ratio = (self.config.upper_price / self.config.lower_price) ** (
                1 / self.config.num_grids
            )
            return round((ratio - 1) * 100, 2)  # percentage

    def _can_invest(self) -> bool:
        """Check if total investment limit allows another grid buy."""
        return (
            self._total_invested + self.config.investment_per_grid
            <= self.config.max_total_investment
        )
