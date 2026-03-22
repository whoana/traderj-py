"""Unit tests for regime-adaptive DCA/Grid configuration."""

from __future__ import annotations

from engine.strategy.dca import DCAConfig
from engine.strategy.grid import GridConfig, GridType
from engine.strategy.regime_config import (
    DCA_RANGING_HIGH_VOL,
    DCA_RANGING_LOW_VOL,
    DCA_REGIME_MAP,
    DCA_TRENDING_HIGH_VOL,
    DCA_TRENDING_LOW_VOL,
    GRID_RANGING_HIGH_VOL,
    GRID_RANGING_LOW_VOL,
    GRID_REGIME_MAP,
    GRID_TRENDING_HIGH_VOL,
    GRID_TRENDING_LOW_VOL,
    build_grid_config,
)
from shared.enums import RegimeType

# ── DCA Regime Preset Tests ──────────────────────────────────────


class TestDCARegimePresets:
    def test_all_regimes_covered(self):
        """DCA_REGIME_MAP should cover all 4 regime types."""
        for rt in RegimeType:
            assert rt in DCA_REGIME_MAP, f"Missing DCA preset for {rt}"

    def test_trending_high_vol_increases_buy(self):
        """Trending high vol should increase buy amount and frequency."""
        base = DCAConfig()
        preset = DCA_TRENDING_HIGH_VOL.config
        assert preset.base_buy_krw > base.base_buy_krw
        assert preset.interval_hours < base.interval_hours

    def test_trending_low_vol_moderate_increase(self):
        """Trending low vol should moderately increase buy amount."""
        base = DCAConfig()
        preset = DCA_TRENDING_LOW_VOL.config
        assert preset.base_buy_krw > base.base_buy_krw
        assert preset.interval_hours < base.interval_hours

    def test_ranging_high_vol_reduces_buy(self):
        """Ranging high vol should reduce buy amount and increase interval."""
        base = DCAConfig()
        preset = DCA_RANGING_HIGH_VOL.config
        assert preset.base_buy_krw < base.base_buy_krw
        assert preset.interval_hours > base.interval_hours

    def test_ranging_low_vol_reduces_buy(self):
        """Ranging low vol should reduce buy amount."""
        base = DCAConfig()
        preset = DCA_RANGING_LOW_VOL.config
        assert preset.base_buy_krw < base.base_buy_krw
        assert preset.interval_hours > base.interval_hours

    def test_trending_has_higher_position_limit(self):
        """Trending presets should allow higher position than ranging."""
        assert DCA_TRENDING_HIGH_VOL.config.max_position_pct > DCA_RANGING_HIGH_VOL.config.max_position_pct
        assert DCA_TRENDING_LOW_VOL.config.max_position_pct > DCA_RANGING_LOW_VOL.config.max_position_pct

    def test_high_vol_has_wider_volatility_cap(self):
        """High vol presets should have wider volatility cap."""
        assert DCA_TRENDING_HIGH_VOL.config.volatility_cap_pct >= DCA_TRENDING_LOW_VOL.config.volatility_cap_pct
        assert DCA_RANGING_HIGH_VOL.config.volatility_cap_pct > DCA_RANGING_LOW_VOL.config.volatility_cap_pct

    def test_all_presets_use_rsi_scaling(self):
        """All DCA presets should use RSI scaling."""
        for preset in DCA_REGIME_MAP.values():
            assert preset.config.use_rsi_scaling is True

    def test_preset_regimes_match_keys(self):
        """Each preset's regime field should match its map key."""
        for regime, preset in DCA_REGIME_MAP.items():
            assert preset.regime == regime


# ── Grid Regime Preset Tests ──────────────────────────────────────


class TestGridRegimePresets:
    def test_all_regimes_covered(self):
        """GRID_REGIME_MAP should cover all 4 regime types."""
        for rt in RegimeType:
            assert rt in GRID_REGIME_MAP, f"Missing Grid preset for {rt}"

    def test_trending_grids_disabled(self):
        """Grid should be disabled for trending regimes."""
        assert GRID_TRENDING_HIGH_VOL.enabled is False
        assert GRID_TRENDING_LOW_VOL.enabled is False

    def test_ranging_grids_enabled(self):
        """Grid should be enabled for ranging regimes."""
        assert GRID_RANGING_HIGH_VOL.enabled is True
        assert GRID_RANGING_LOW_VOL.enabled is True

    def test_high_vol_wider_range(self):
        """High vol ranging should have wider range than low vol."""
        assert GRID_RANGING_HIGH_VOL.range_pct > GRID_RANGING_LOW_VOL.range_pct

    def test_low_vol_more_grids(self):
        """Low vol ranging should have more (tighter) grids."""
        assert GRID_RANGING_LOW_VOL.grid_count > GRID_RANGING_HIGH_VOL.grid_count

    def test_high_vol_uses_geometric(self):
        """High vol should use geometric grid (% spacing)."""
        assert GRID_RANGING_HIGH_VOL.grid_type == GridType.GEOMETRIC

    def test_low_vol_uses_arithmetic(self):
        """Low vol should use arithmetic grid (equal spacing)."""
        assert GRID_RANGING_LOW_VOL.grid_type == GridType.ARITHMETIC

    def test_disabled_presets_have_zero_values(self):
        """Disabled grid presets should have zero grid_count and investment."""
        for preset in [GRID_TRENDING_HIGH_VOL, GRID_TRENDING_LOW_VOL]:
            assert preset.grid_count == 0
            assert preset.investment_per_grid == 0

    def test_preset_regimes_match_keys(self):
        """Each preset's regime field should match its map key."""
        for regime, preset in GRID_REGIME_MAP.items():
            assert preset.regime == regime


# ── build_grid_config Tests ──────────────────────────────────────


class TestBuildGridConfig:
    def test_returns_none_when_disabled(self):
        """build_grid_config should return None for disabled presets."""
        result = build_grid_config(GRID_TRENDING_HIGH_VOL, 90_000_000)
        assert result is None

    def test_returns_none_for_zero_price(self):
        """build_grid_config should return None for zero/negative price."""
        assert build_grid_config(GRID_RANGING_HIGH_VOL, 0) is None
        assert build_grid_config(GRID_RANGING_HIGH_VOL, -1) is None

    def test_returns_grid_config_when_enabled(self):
        """build_grid_config should return GridConfig for enabled presets."""
        result = build_grid_config(GRID_RANGING_HIGH_VOL, 90_000_000)
        assert result is not None
        assert isinstance(result, GridConfig)

    def test_price_range_symmetric(self):
        """Grid range should be symmetric around current price."""
        price = 90_000_000
        result = build_grid_config(GRID_RANGING_HIGH_VOL, price)
        assert result is not None

        mid = (result.upper_price + result.lower_price) / 2
        assert abs(mid - price) < 1  # rounding tolerance

    def test_range_matches_preset_pct(self):
        """Grid range should match the preset's range_pct."""
        price = 90_000_000
        preset = GRID_RANGING_HIGH_VOL
        result = build_grid_config(preset, price)
        assert result is not None

        actual_range = result.upper_price - result.lower_price
        expected_range = price * preset.range_pct
        assert abs(actual_range - expected_range) < 2  # rounding tolerance

    def test_num_grids_from_preset(self):
        """num_grids should match the preset's grid_count."""
        result = build_grid_config(GRID_RANGING_HIGH_VOL, 90_000_000)
        assert result is not None
        assert result.num_grids == GRID_RANGING_HIGH_VOL.grid_count

    def test_grid_type_from_preset(self):
        """grid_type should match the preset."""
        result = build_grid_config(GRID_RANGING_HIGH_VOL, 90_000_000)
        assert result is not None
        assert result.grid_type == GridType.GEOMETRIC

    def test_max_total_investment(self):
        """max_total_investment should be investment_per_grid × grid_count."""
        preset = GRID_RANGING_LOW_VOL
        result = build_grid_config(preset, 90_000_000)
        assert result is not None
        assert result.max_total_investment == preset.investment_per_grid * preset.grid_count

    def test_low_vol_config(self):
        """Low vol grid should produce a tighter range."""
        price = 90_000_000
        high_vol = build_grid_config(GRID_RANGING_HIGH_VOL, price)
        low_vol = build_grid_config(GRID_RANGING_LOW_VOL, price)
        assert high_vol is not None and low_vol is not None

        high_range = high_vol.upper_price - high_vol.lower_price
        low_range = low_vol.upper_price - low_vol.lower_price
        assert high_range > low_range
