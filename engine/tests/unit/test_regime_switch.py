"""Tests for automatic strategy switching."""

from datetime import UTC, datetime, timedelta

from engine.strategy.regime import RegimeResult
from engine.strategy.regime_switch import (
    RegimeSwitchConfig,
    RegimeSwitchManager,
)
from shared.enums import RegimeType


def _regime(regime: RegimeType, confidence: float = 0.5) -> RegimeResult:
    return RegimeResult(
        regime=regime, adx=30, bb_width=0.05,
        dmp=20, dmn=10,
        trend_strength=0.5, volatility_level=0.5,
        confidence=confidence,
    )


class TestDebounce:
    def test_single_detection_no_switch(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=3))
        mgr.set_initial_preset("STR-001")
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL

        decision = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        assert decision.should_switch is False
        assert "debounce" in decision.reason

    def test_consecutive_detections_trigger_switch(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=3))
        mgr.set_initial_preset("STR-001")
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL

        new_regime = RegimeType.RANGING_HIGH_VOL
        mgr.evaluate(_regime(new_regime))
        mgr.evaluate(_regime(new_regime))
        decision = mgr.evaluate(_regime(new_regime))

        assert decision.should_switch is True
        assert decision.recommended_preset == "STR-003"

    def test_mixed_detections_reset_debounce(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=3))
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL

        mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        # Different regime resets counter
        mgr.evaluate(_regime(RegimeType.RANGING_LOW_VOL))
        decision = mgr.evaluate(_regime(RegimeType.RANGING_LOW_VOL))

        assert decision.should_switch is False
        assert decision.consecutive_detections == 2

    def test_same_regime_no_switch(self):
        mgr = RegimeSwitchManager()
        mgr._current_regime = RegimeType.BULL_TREND_HIGH_VOL

        decision = mgr.evaluate(_regime(RegimeType.BULL_TREND_HIGH_VOL))
        assert decision.should_switch is False
        assert decision.reason == "same_regime"


class TestCooldown:
    def test_cooldown_blocks_switch(self):
        mgr = RegimeSwitchManager(
            config=RegimeSwitchConfig(debounce_count=1, cooldown_minutes=60)
        )
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL

        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

        # First switch
        d1 = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL), now=now)
        assert d1.should_switch is True
        mgr.apply_switch(d1, now=now)

        # 30 min later → blocked
        later = now + timedelta(minutes=30)
        d2 = mgr.evaluate(_regime(RegimeType.BULL_TREND_LOW_VOL), now=later)
        assert d2.should_switch is False
        assert "cooldown" in d2.reason

    def test_cooldown_expired_allows(self):
        mgr = RegimeSwitchManager(
            config=RegimeSwitchConfig(debounce_count=1, cooldown_minutes=60)
        )
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

        d1 = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL), now=now)
        mgr.apply_switch(d1, now=now)

        later = now + timedelta(minutes=61)
        d2 = mgr.evaluate(_regime(RegimeType.BULL_TREND_LOW_VOL), now=later)
        assert d2.should_switch is True


class TestApplySwitch:
    def test_apply_updates_state(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=1))
        mgr.set_initial_preset("STR-001")
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL

        decision = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        new_preset = mgr.apply_switch(decision)

        assert new_preset == "STR-003"
        assert mgr.current_preset == "STR-003"
        assert mgr.current_regime == RegimeType.RANGING_HIGH_VOL
        assert mgr.switch_count == 1

    def test_switch_history_tracked(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=1))
        mgr.set_initial_preset("STR-001")
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL

        d = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        mgr.apply_switch(d)

        history = mgr.get_history()
        assert len(history) == 1
        assert history[0]["old_preset"] == "STR-001"
        assert history[0]["new_preset"] == "STR-003"


class TestLocking:
    def test_lock_prevents_switch(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=1))
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL
        mgr.lock()

        decision = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        assert decision.should_switch is False
        assert decision.reason == "manually_locked"

    def test_unlock_allows_switch(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=1))
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL
        mgr.lock()
        mgr.unlock()

        decision = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        assert decision.should_switch is True


class TestDisabled:
    def test_disabled_no_switch(self):
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(enabled=False))
        mgr._current_regime = RegimeType.BULL_TREND_LOW_VOL

        decision = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        assert decision.should_switch is False
        assert decision.reason == "auto_switch_disabled"


class TestDCAGridIntegration:
    def test_get_dca_config_for_current_regime(self):
        """get_dca_config returns DCA config matching current regime."""
        mgr = RegimeSwitchManager()
        mgr._current_regime = RegimeType.BULL_TREND_HIGH_VOL

        dca = mgr.get_dca_config()
        assert dca is not None
        assert dca.base_buy_krw == 150_000
        assert dca.interval_hours == 12

    def test_get_dca_config_explicit_regime(self):
        """get_dca_config accepts explicit regime parameter."""
        mgr = RegimeSwitchManager()
        mgr._current_regime = RegimeType.BULL_TREND_HIGH_VOL

        dca = mgr.get_dca_config(regime=RegimeType.RANGING_LOW_VOL)
        assert dca is not None
        assert dca.base_buy_krw == 80_000

    def test_get_dca_config_no_regime(self):
        """get_dca_config returns None when no regime set."""
        mgr = RegimeSwitchManager()
        assert mgr.get_dca_config() is None

    def test_get_grid_config_ranging(self):
        """get_grid_config returns GridConfig for ranging regimes."""
        mgr = RegimeSwitchManager()
        mgr._current_regime = RegimeType.RANGING_HIGH_VOL

        grid = mgr.get_grid_config(current_price=90_000_000)
        assert grid is not None
        assert grid.num_grids == 8
        assert grid.grid_type.value == "geometric"

    def test_get_grid_config_trending_returns_none(self):
        """get_grid_config returns None for trending regimes (grid disabled)."""
        mgr = RegimeSwitchManager()
        mgr._current_regime = RegimeType.BULL_TREND_HIGH_VOL

        grid = mgr.get_grid_config(current_price=90_000_000)
        assert grid is None

    def test_get_grid_config_no_regime(self):
        """get_grid_config returns None when no regime set."""
        mgr = RegimeSwitchManager()
        assert mgr.get_grid_config(current_price=90_000_000) is None

    def test_dca_grid_change_after_switch(self):
        """DCA/Grid configs should change after regime switch."""
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=1))
        mgr._current_regime = RegimeType.BULL_TREND_HIGH_VOL

        # Trending: DCA active, Grid disabled
        dca_before = mgr.get_dca_config()
        grid_before = mgr.get_grid_config(90_000_000)
        assert dca_before is not None
        assert dca_before.base_buy_krw == 150_000
        assert grid_before is None

        # Switch to ranging
        d = mgr.evaluate(_regime(RegimeType.RANGING_LOW_VOL))
        mgr.apply_switch(d)

        # Ranging: DCA reduced, Grid active
        dca_after = mgr.get_dca_config()
        grid_after = mgr.get_grid_config(90_000_000)
        assert dca_after is not None
        assert dca_after.base_buy_krw == 80_000
        assert grid_after is not None
        assert grid_after.num_grids == 12


class TestBearRegimeSwitch:
    def test_bull_to_bear_switch(self):
        """Bull trend → Bear trend switch after debounce."""
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=3))
        mgr.set_initial_preset("STR-002")
        mgr._current_regime = RegimeType.BULL_TREND_HIGH_VOL

        bear = RegimeType.BEAR_TREND_HIGH_VOL
        mgr.evaluate(_regime(bear))
        mgr.evaluate(_regime(bear))
        d = mgr.evaluate(_regime(bear))

        assert d.should_switch is True
        assert d.recommended_preset == "STR-007"

    def test_bear_to_ranging_switch(self):
        """Bear trend → Ranging switch activates grid."""
        mgr = RegimeSwitchManager(config=RegimeSwitchConfig(debounce_count=1))
        mgr.set_initial_preset("STR-007")
        mgr._current_regime = RegimeType.BEAR_TREND_HIGH_VOL

        d = mgr.evaluate(_regime(RegimeType.RANGING_HIGH_VOL))
        assert d.should_switch is True
        new_preset = mgr.apply_switch(d)
        assert new_preset == "STR-003"

        grid = mgr.get_grid_config(90_000_000)
        assert grid is not None

    def test_bear_dca_has_smaller_amount(self):
        """Bear DCA should have much smaller buy amount than bull."""
        mgr = RegimeSwitchManager()
        mgr._current_regime = RegimeType.BEAR_TREND_HIGH_VOL
        bear_dca = mgr.get_dca_config()
        assert bear_dca is not None
        assert bear_dca.base_buy_krw == 30_000

        mgr._current_regime = RegimeType.BULL_TREND_HIGH_VOL
        bull_dca = mgr.get_dca_config()
        assert bull_dca is not None
        assert bull_dca.base_buy_krw > bear_dca.base_buy_krw

    def test_bear_grid_disabled(self):
        """Grid should be disabled in bear trend."""
        mgr = RegimeSwitchManager()
        mgr._current_regime = RegimeType.BEAR_TREND_HIGH_VOL
        assert mgr.get_grid_config(90_000_000) is None

        mgr._current_regime = RegimeType.BEAR_TREND_LOW_VOL
        assert mgr.get_grid_config(90_000_000) is None
