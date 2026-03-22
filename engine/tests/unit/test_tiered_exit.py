"""Tests for tiered exit strategy."""

from decimal import Decimal

import pytest

from engine.strategy.tiered_exit import (
    TieredExitConfig,
    TieredExitManager,
)


class TestPlanCreation:
    def test_default_plan_3_tiers(self):
        mgr = TieredExitManager()
        plan = mgr.create_plan(
            strategy_id="STR-001",
            entry_price=Decimal("95000000"),
            current_atr=Decimal("2000000"),
        )

        assert len(plan["sl_tiers"]) == 3
        assert len(plan["tp_tiers"]) == 3

    def test_sl_tiers_descending(self):
        mgr = TieredExitManager()
        plan = mgr.create_plan(
            strategy_id="STR-001",
            entry_price=Decimal("95000000"),
            current_atr=Decimal("2000000"),
        )

        sl = plan["sl_tiers"]
        # Tier 1 (1.5x ATR) > Tier 2 (2.0x ATR) > Tier 3 (3.0x ATR)
        assert sl[0].price > sl[1].price > sl[2].price

    def test_tp_tiers_ascending(self):
        mgr = TieredExitManager()
        plan = mgr.create_plan(
            strategy_id="STR-001",
            entry_price=Decimal("95000000"),
            current_atr=Decimal("2000000"),
        )

        tp = plan["tp_tiers"]
        assert tp[0].price < tp[1].price < tp[2].price

    def test_tier_percentages_sum_to_1(self):
        mgr = TieredExitManager()
        plan = mgr.create_plan(
            strategy_id="STR-001",
            entry_price=Decimal("95000000"),
            current_atr=Decimal("2000000"),
        )

        sl_total = sum(t.pct_of_position for t in plan["sl_tiers"])
        tp_total = sum(t.pct_of_position for t in plan["tp_tiers"])
        assert abs(sl_total - 1.0) < 0.001
        assert abs(tp_total - 1.0) < 0.001

    def test_custom_config(self):
        config = TieredExitConfig(
            sl_tier_pcts=(0.60, 0.40),
            sl_atr_multipliers=(1.0, 2.0),
            tp_tier_pcts=(0.60, 0.40),
            tp_rr_multipliers=(1.0, 3.0),
        )
        mgr = TieredExitManager(config=config)
        plan = mgr.create_plan(
            strategy_id="STR-001",
            entry_price=Decimal("100000000"),
            current_atr=Decimal("3000000"),
        )

        assert len(plan["sl_tiers"]) == 2
        assert len(plan["tp_tiers"]) == 2

    def test_sl_price_calculation(self):
        mgr = TieredExitManager()
        plan = mgr.create_plan(
            strategy_id="STR-001",
            entry_price=Decimal("100000000"),
            current_atr=Decimal("2000000"),
        )

        sl = plan["sl_tiers"]
        # Tier 1: 100M - 1.5*2M = 97M
        assert sl[0].price == Decimal("97000000")
        # Tier 2: 100M - 2.0*2M = 96M
        assert sl[1].price == Decimal("96000000")
        # Tier 3: 100M - 3.0*2M = 94M
        assert sl[2].price == Decimal("94000000")


class TestEvaluation:
    def _setup(self):
        mgr = TieredExitManager()
        mgr.create_plan(
            strategy_id="STR-001",
            entry_price=Decimal("100000000"),
            current_atr=Decimal("2000000"),
        )
        return mgr

    def test_no_trigger_in_range(self):
        mgr = self._setup()
        action = mgr.evaluate("STR-001", Decimal("99000000"))
        assert action.should_exit is False

    def test_sl_tier1_triggers(self):
        mgr = self._setup()
        # SL Tier 1 = 97M
        action = mgr.evaluate("STR-001", Decimal("96500000"))
        assert action.should_exit is True
        assert action.exit_type == "stop_loss"
        assert action.tier == 1
        assert action.exit_pct == 0.50

    def test_tp_tier1_triggers(self):
        mgr = self._setup()
        # Risk = 100M - 97M = 3M, TP Tier 1 = 100M + 3M*1.5 = 104.5M
        plan = mgr.get_plan("STR-001")
        tp1_price = plan["tp_tiers"][0].price
        action = mgr.evaluate("STR-001", tp1_price + Decimal("100000"))
        assert action.should_exit is True
        assert action.exit_type == "take_profit"
        assert action.tier == 1
        assert action.exit_pct == 0.50

    def test_triggered_tier_skipped(self):
        mgr = self._setup()
        # Trigger tier 1
        action = mgr.evaluate("STR-001", Decimal("96000000"))
        assert action.tier == 1
        mgr.mark_triggered("STR-001", "stop_loss", 1)

        # Same price → tier 2 triggers now
        action2 = mgr.evaluate("STR-001", Decimal("96000000"))
        assert action2.should_exit is True
        assert action2.tier == 2
        assert action2.exit_pct == 0.30

    def test_all_tiers_triggered(self):
        mgr = self._setup()
        # Trigger all SL tiers
        mgr.mark_triggered("STR-001", "stop_loss", 1)
        mgr.mark_triggered("STR-001", "stop_loss", 2)
        mgr.mark_triggered("STR-001", "stop_loss", 3)

        action = mgr.evaluate("STR-001", Decimal("93000000"))
        assert action.should_exit is False

    def test_no_plan_returns_no_exit(self):
        mgr = TieredExitManager()
        action = mgr.evaluate("UNKNOWN", Decimal("95000000"))
        assert action.should_exit is False
        assert action.reason == "no_plan"


class TestPositionTracking:
    def test_remaining_after_tier1(self):
        mgr = TieredExitManager()
        mgr.create_plan("STR-001", Decimal("100000000"), Decimal("2000000"))
        mgr.mark_triggered("STR-001", "stop_loss", 1)

        assert mgr.remaining_position_pct("STR-001") == 0.50

    def test_remaining_after_tier1_and_2(self):
        mgr = TieredExitManager()
        mgr.create_plan("STR-001", Decimal("100000000"), Decimal("2000000"))
        mgr.mark_triggered("STR-001", "stop_loss", 1)
        mgr.mark_triggered("STR-001", "stop_loss", 2)

        assert mgr.remaining_position_pct("STR-001") == pytest.approx(0.20)

    def test_remaining_no_plan(self):
        mgr = TieredExitManager()
        assert mgr.remaining_position_pct("UNKNOWN") == 1.0

    def test_remove_plan(self):
        mgr = TieredExitManager()
        mgr.create_plan("STR-001", Decimal("100000000"), Decimal("2000000"))
        mgr.remove_plan("STR-001")
        assert mgr.get_plan("STR-001") is None
