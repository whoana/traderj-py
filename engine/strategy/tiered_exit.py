"""Tiered (stepped) exit strategy — partial position liquidation at multiple levels.

Instead of a single all-or-nothing stop loss, closes the position in tiers:
  - Tier 1: Close 50% at first stop level (tightest)
  - Tier 2: Close 30% at second stop level
  - Tier 3: Close remaining 20% at final stop level (widest)

Also supports tiered take-profit:
  - TP Tier 1: Close 50% at first TP level
  - TP Tier 2: Close 30% at second TP level
  - TP Tier 3: Close remaining 20% at final TP level
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TierLevel:
    """A single tier in the exit plan."""

    tier: int
    price: Decimal
    pct_of_position: float  # 0.0~1.0 fraction of remaining position
    triggered: bool = False


@dataclass(frozen=True)
class TieredExitConfig:
    """Tiered exit parameters."""

    # Stop loss tiers (fractions of position to close)
    sl_tier_pcts: tuple[float, ...] = (0.50, 0.30, 0.20)
    # ATR multipliers for each SL tier (increasing distance)
    sl_atr_multipliers: tuple[float, ...] = (1.5, 2.0, 3.0)

    # Take profit tiers
    tp_tier_pcts: tuple[float, ...] = (0.50, 0.30, 0.20)
    # R:R multipliers for each TP tier (increasing targets)
    tp_rr_multipliers: tuple[float, ...] = (1.5, 2.5, 4.0)


@dataclass
class TieredExitAction:
    """Result from tiered exit evaluation."""

    should_exit: bool
    exit_type: str = "none"  # "stop_loss" | "take_profit" | "none"
    tier: int = 0
    exit_pct: float = 0.0  # fraction of current position to close
    trigger_price: Decimal = Decimal("0")
    level_price: Decimal = Decimal("0")
    reason: str = ""


class TieredExitManager:
    """Manages tiered stop-loss and take-profit exits."""

    def __init__(
        self,
        config: TieredExitConfig | None = None,
    ) -> None:
        self.config = config or TieredExitConfig()
        # Per-strategy exit plans: {strategy_id: {"sl_tiers": [...], "tp_tiers": [...]}}
        self._plans: dict[str, dict[str, list[TierLevel]]] = {}

    def create_plan(
        self,
        strategy_id: str,
        entry_price: Decimal,
        current_atr: Decimal,
    ) -> dict[str, list[TierLevel]]:
        """Create a tiered exit plan for a new position.

        Args:
            strategy_id: Strategy identifier.
            entry_price: Position entry price.
            current_atr: Current ATR value.

        Returns:
            Dict with "sl_tiers" and "tp_tiers" lists.
        """
        sl_tiers = []
        for i, (pct, mult) in enumerate(
            zip(self.config.sl_tier_pcts, self.config.sl_atr_multipliers, strict=True)
        ):
            sl_price = entry_price - current_atr * Decimal(str(mult))
            sl_tiers.append(TierLevel(
                tier=i + 1,
                price=max(Decimal("0"), sl_price),
                pct_of_position=pct,
            ))

        tp_tiers = []
        # Risk per unit = entry - first SL tier
        risk = entry_price - sl_tiers[0].price if sl_tiers else current_atr
        for i, (pct, mult) in enumerate(
            zip(self.config.tp_tier_pcts, self.config.tp_rr_multipliers, strict=True)
        ):
            tp_price = entry_price + risk * Decimal(str(mult))
            tp_tiers.append(TierLevel(
                tier=i + 1,
                price=tp_price,
                pct_of_position=pct,
            ))

        plan = {"sl_tiers": sl_tiers, "tp_tiers": tp_tiers}
        self._plans[strategy_id] = plan

        logger.info(
            "Tiered exit plan for %s: SL=[%s], TP=[%s]",
            strategy_id,
            ", ".join(f"T{t.tier}:{t.price:.0f}({t.pct_of_position:.0%})" for t in sl_tiers),
            ", ".join(f"T{t.tier}:{t.price:.0f}({t.pct_of_position:.0%})" for t in tp_tiers),
        )

        return plan

    def evaluate(
        self,
        strategy_id: str,
        current_price: Decimal,
    ) -> TieredExitAction:
        """Evaluate current price against tiered exit plan.

        Returns the highest-priority exit action (TP checked first).
        """
        plan = self._plans.get(strategy_id)
        if plan is None:
            return TieredExitAction(should_exit=False, reason="no_plan")

        # Check take-profit tiers (ascending order — lowest target first)
        for tier in plan["tp_tiers"]:
            if tier.triggered:
                continue
            if current_price >= tier.price:
                return TieredExitAction(
                    should_exit=True,
                    exit_type="take_profit",
                    tier=tier.tier,
                    exit_pct=tier.pct_of_position,
                    trigger_price=current_price,
                    level_price=tier.price,
                    reason=f"tp_tier_{tier.tier}",
                )

        # Check stop-loss tiers (descending order — highest stop first / tightest)
        for tier in plan["sl_tiers"]:
            if tier.triggered:
                continue
            if current_price <= tier.price:
                return TieredExitAction(
                    should_exit=True,
                    exit_type="stop_loss",
                    tier=tier.tier,
                    exit_pct=tier.pct_of_position,
                    trigger_price=current_price,
                    level_price=tier.price,
                    reason=f"sl_tier_{tier.tier}",
                )

        return TieredExitAction(should_exit=False, reason="no_trigger")

    def mark_triggered(self, strategy_id: str, exit_type: str, tier: int) -> None:
        """Mark a tier as triggered after execution."""
        plan = self._plans.get(strategy_id)
        if plan is None:
            return

        key = "tp_tiers" if exit_type == "take_profit" else "sl_tiers"
        tiers = plan[key]
        for i, t in enumerate(tiers):
            if t.tier == tier:
                tiers[i] = TierLevel(
                    tier=t.tier,
                    price=t.price,
                    pct_of_position=t.pct_of_position,
                    triggered=True,
                )
                logger.info(
                    "Tier %d %s triggered for %s at %s",
                    tier, exit_type, strategy_id, t.price,
                )
                break

    def remove_plan(self, strategy_id: str) -> None:
        """Remove exit plan when position is fully closed."""
        self._plans.pop(strategy_id, None)

    def get_plan(self, strategy_id: str) -> dict[str, list[TierLevel]] | None:
        """Get the exit plan for a strategy."""
        return self._plans.get(strategy_id)

    def remaining_position_pct(self, strategy_id: str) -> float:
        """Calculate remaining position percentage after triggered tiers."""
        plan = self._plans.get(strategy_id)
        if plan is None:
            return 1.0

        exited = 0.0
        for tier in plan["sl_tiers"] + plan["tp_tiers"]:
            if tier.triggered:
                exited += tier.pct_of_position

        return max(0.0, 1.0 - exited)
