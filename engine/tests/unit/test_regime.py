"""Tests for market regime detection."""

import pandas as pd

from engine.strategy.regime import (
    REGIME_PRESET_MAP,
    RegimeConfig,
    detect_regime,
)
from shared.enums import RegimeType


def _make_df(adx_vals: list[float], bb_width_vals: list[float]) -> pd.DataFrame:
    """Create a minimal DataFrame with adx and bb_width columns."""
    n = max(len(adx_vals), len(bb_width_vals), 30)
    # Pad with NaN to reach min_bars
    adx_padded = [float("nan")] * (n - len(adx_vals)) + adx_vals
    bb_padded = [float("nan")] * (n - len(bb_width_vals)) + bb_width_vals
    return pd.DataFrame({"adx": adx_padded, "bb_width": bb_padded})


class TestRegimeDetection:
    def test_trending_high_vol(self):
        df = _make_df([35, 38, 40], [0.06, 0.07, 0.08])
        result = detect_regime(df)
        assert result.regime == RegimeType.TRENDING_HIGH_VOL
        assert result.adx > 25

    def test_trending_low_vol(self):
        df = _make_df([30, 32, 35], [0.02, 0.025, 0.03])
        result = detect_regime(df)
        assert result.regime == RegimeType.TRENDING_LOW_VOL

    def test_ranging_high_vol(self):
        df = _make_df([15, 18, 20], [0.06, 0.07, 0.05])
        result = detect_regime(df)
        assert result.regime == RegimeType.RANGING_HIGH_VOL

    def test_ranging_low_vol(self):
        df = _make_df([10, 12, 15], [0.02, 0.01, 0.015])
        result = detect_regime(df)
        assert result.regime == RegimeType.RANGING_LOW_VOL

    def test_insufficient_data(self):
        df = pd.DataFrame({"adx": [30], "bb_width": [0.05]})
        result = detect_regime(df)
        assert result.regime == RegimeType.RANGING_LOW_VOL
        assert result.confidence == 0.0

    def test_custom_thresholds(self):
        config = RegimeConfig(adx_trend_threshold=20.0, bb_width_vol_threshold=0.03)
        df = _make_df([22, 23, 24], [0.035, 0.04, 0.038])
        result = detect_regime(df, config=config)
        assert result.regime == RegimeType.TRENDING_HIGH_VOL

    def test_confidence_high_when_clear(self):
        # ADX=50 (far above 25), BB_Width=0.08 (far above 0.04)
        df = _make_df([50, 50, 50], [0.08, 0.08, 0.08])
        result = detect_regime(df)
        assert result.confidence > 0.5

    def test_confidence_low_near_thresholds(self):
        # ADX=26 (barely above 25), BB_Width=0.041 (barely above 0.04)
        df = _make_df([26, 26, 26], [0.041, 0.041, 0.041])
        result = detect_regime(df)
        assert result.confidence < 0.1

    def test_trend_strength_normalized(self):
        df = _make_df([50, 50, 50], [0.05, 0.05, 0.05])
        result = detect_regime(df)
        assert result.trend_strength == 1.0  # 50/50 capped at 1.0

    def test_volatility_level_normalized(self):
        df = _make_df([30, 30, 30], [0.10, 0.10, 0.10])
        result = detect_regime(df)
        assert result.volatility_level == 1.0  # 0.10/0.10 capped at 1.0

    def test_smoothing_uses_last_n_bars(self):
        config = RegimeConfig(smoothing_period=3)
        # Last 3 bars: trending. Earlier bars: ranging (should be ignored)
        adx = [10, 10, 10, 10, 10] + [35, 38, 40]
        bb = [0.02] * 5 + [0.05, 0.06, 0.07]
        df = _make_df(adx, bb)
        result = detect_regime(df, config=config)
        assert result.regime == RegimeType.TRENDING_HIGH_VOL


class TestPresetMapping:
    def test_all_regimes_have_preset(self):
        for regime in RegimeType:
            assert regime in REGIME_PRESET_MAP

    def test_trending_maps_to_trend_strategies(self):
        assert REGIME_PRESET_MAP[RegimeType.TRENDING_HIGH_VOL] == "STR-002"
        assert REGIME_PRESET_MAP[RegimeType.TRENDING_LOW_VOL] == "STR-001"

    def test_ranging_maps_to_reversal_or_conservative(self):
        assert REGIME_PRESET_MAP[RegimeType.RANGING_HIGH_VOL] == "STR-003"
        assert REGIME_PRESET_MAP[RegimeType.RANGING_LOW_VOL] == "STR-005"
