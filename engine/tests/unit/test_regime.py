"""Tests for market regime detection (6-type: bull/bear/ranging × high/low vol)."""

import pandas as pd

from engine.strategy.regime import (
    REGIME_PRESET_MAP,
    RegimeConfig,
    detect_regime,
)
from shared.enums import RegimeType


def _make_df(
    adx_vals: list[float],
    bb_width_vals: list[float],
    dmp_vals: list[float] | None = None,
    dmn_vals: list[float] | None = None,
) -> pd.DataFrame:
    """Create a minimal DataFrame with adx, bb_width, dmp, dmn columns."""
    n = max(len(adx_vals), len(bb_width_vals), 30)
    adx_padded = [float("nan")] * (n - len(adx_vals)) + adx_vals
    bb_padded = [float("nan")] * (n - len(bb_width_vals)) + bb_width_vals

    data: dict[str, list[float]] = {"adx": adx_padded, "bb_width": bb_padded}

    if dmp_vals is not None:
        data["dmp"] = [float("nan")] * (n - len(dmp_vals)) + dmp_vals
    if dmn_vals is not None:
        data["dmn"] = [float("nan")] * (n - len(dmn_vals)) + dmn_vals

    return pd.DataFrame(data)


class TestRegimeDetection:
    # --- Bull trend ---
    def test_bull_trend_high_vol(self):
        df = _make_df([35, 38, 40], [0.06, 0.07, 0.08], [30, 32, 35], [15, 14, 12])
        result = detect_regime(df)
        assert result.regime == RegimeType.BULL_TREND_HIGH_VOL
        assert result.adx > 25
        assert result.dmp > result.dmn

    def test_bull_trend_low_vol(self):
        df = _make_df([30, 32, 35], [0.02, 0.025, 0.03], [28, 30, 32], [12, 11, 10])
        result = detect_regime(df)
        assert result.regime == RegimeType.BULL_TREND_LOW_VOL

    # --- Bear trend ---
    def test_bear_trend_high_vol(self):
        df = _make_df([35, 38, 40], [0.06, 0.07, 0.08], [12, 14, 15], [30, 32, 35])
        result = detect_regime(df)
        assert result.regime == RegimeType.BEAR_TREND_HIGH_VOL
        assert result.dmn > result.dmp

    def test_bear_trend_low_vol(self):
        df = _make_df([30, 32, 35], [0.02, 0.025, 0.03], [10, 11, 12], [28, 30, 32])
        result = detect_regime(df)
        assert result.regime == RegimeType.BEAR_TREND_LOW_VOL

    # --- Ranging (direction doesn't matter) ---
    def test_ranging_high_vol(self):
        df = _make_df([15, 18, 20], [0.06, 0.07, 0.05], [15, 16, 14], [14, 15, 16])
        result = detect_regime(df)
        assert result.regime == RegimeType.RANGING_HIGH_VOL

    def test_ranging_low_vol(self):
        df = _make_df([10, 12, 15], [0.02, 0.01, 0.015], [10, 11, 12], [13, 14, 15])
        result = detect_regime(df)
        assert result.regime == RegimeType.RANGING_LOW_VOL

    # --- Edge cases ---
    def test_insufficient_data(self):
        df = pd.DataFrame({"adx": [30], "bb_width": [0.05], "dmp": [20], "dmn": [10]})
        result = detect_regime(df)
        assert result.regime == RegimeType.RANGING_LOW_VOL
        assert result.confidence == 0.0

    def test_no_dmp_dmn_defaults_to_bullish(self):
        """Without DMP/DMN columns, trending defaults to bullish (dmp=dmn=0, >=)."""
        df = _make_df([35, 38, 40], [0.06, 0.07, 0.08])
        result = detect_regime(df)
        assert result.regime == RegimeType.BULL_TREND_HIGH_VOL

    def test_equal_dmp_dmn_defaults_to_bullish(self):
        """DMP == DMN → bullish (>= comparison)."""
        df = _make_df([35, 38, 40], [0.06, 0.07, 0.08], [20, 20, 20], [20, 20, 20])
        result = detect_regime(df)
        assert result.regime == RegimeType.BULL_TREND_HIGH_VOL

    def test_custom_thresholds(self):
        config = RegimeConfig(adx_trend_threshold=20.0, bb_width_vol_threshold=0.03)
        df = _make_df([22, 23, 24], [0.035, 0.04, 0.038], [18, 19, 20], [10, 11, 12])
        result = detect_regime(df, config=config)
        assert result.regime == RegimeType.BULL_TREND_HIGH_VOL

    def test_confidence_high_when_clear(self):
        df = _make_df([50, 50, 50], [0.08, 0.08, 0.08], [40, 40, 40], [10, 10, 10])
        result = detect_regime(df)
        assert result.confidence > 0.5

    def test_confidence_low_near_thresholds(self):
        df = _make_df([26, 26, 26], [0.041, 0.041, 0.041], [15, 15, 15], [12, 12, 12])
        result = detect_regime(df)
        assert result.confidence < 0.1

    def test_trend_strength_normalized(self):
        df = _make_df([50, 50, 50], [0.05, 0.05, 0.05], [30, 30, 30], [10, 10, 10])
        result = detect_regime(df)
        assert result.trend_strength == 1.0

    def test_volatility_level_normalized(self):
        df = _make_df([30, 30, 30], [0.10, 0.10, 0.10], [20, 20, 20], [10, 10, 10])
        result = detect_regime(df)
        assert result.volatility_level == 1.0

    def test_smoothing_uses_last_n_bars(self):
        config = RegimeConfig(smoothing_period=3)
        adx = [10, 10, 10, 10, 10] + [35, 38, 40]
        bb = [0.02] * 5 + [0.05, 0.06, 0.07]
        dmp = [10] * 5 + [30, 32, 35]
        dmn = [20] * 5 + [12, 11, 10]
        df = _make_df(adx, bb, dmp, dmn)
        result = detect_regime(df, config=config)
        assert result.regime == RegimeType.BULL_TREND_HIGH_VOL

    def test_result_includes_dmp_dmn(self):
        df = _make_df([35, 35, 35], [0.05, 0.05, 0.05], [25, 25, 25], [10, 10, 10])
        result = detect_regime(df)
        assert result.dmp == 25.0
        assert result.dmn == 10.0


class TestPresetMapping:
    def test_all_regimes_have_preset(self):
        for regime in RegimeType:
            assert regime in REGIME_PRESET_MAP

    def test_bull_trend_maps_to_trend_strategies(self):
        assert REGIME_PRESET_MAP[RegimeType.BULL_TREND_HIGH_VOL] == "STR-002"
        assert REGIME_PRESET_MAP[RegimeType.BULL_TREND_LOW_VOL] == "STR-001"

    def test_bear_trend_maps_to_bear_strategies(self):
        assert REGIME_PRESET_MAP[RegimeType.BEAR_TREND_HIGH_VOL] == "STR-007"
        assert REGIME_PRESET_MAP[RegimeType.BEAR_TREND_LOW_VOL] == "STR-008"

    def test_ranging_maps_to_reversal_or_conservative(self):
        assert REGIME_PRESET_MAP[RegimeType.RANGING_HIGH_VOL] == "STR-003"
        assert REGIME_PRESET_MAP[RegimeType.RANGING_LOW_VOL] == "STR-005"
