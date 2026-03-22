"""Unit tests for indicator pipeline and Z-score normalization.

Validates 5 core indicators (EMA, BB, RSI, MACD, ATR) and
the full compute_indicators() + normalize_indicators() chain.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.strategy.indicators import IndicatorConfig, compute_indicators
from engine.strategy.normalizer import (
    normalize_indicators,
    z_score,
    z_to_score,
)


@pytest.fixture()
def ohlcv_350() -> pd.DataFrame:
    """Generate synthetic OHLCV data with 350 bars for testing."""
    np.random.seed(42)
    n = 350
    # Start with a base price and add trending + random walk
    base = 50_000_000.0  # 50M KRW for BTC/KRW
    returns = np.random.normal(0.001, 0.02, n)
    close = base * np.cumprod(1 + returns)

    # Create OHLCV from close prices
    high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_ = close * (1 + np.random.normal(0, 0.005, n))
    volume = np.abs(np.random.normal(100, 30, n))

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestComputeIndicators:
    """Test compute_indicators() function."""

    def test_returns_new_dataframe(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        assert result is not ohlcv_350

    def test_preserves_original_columns(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in result.columns

    def test_adds_ema_columns(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        for col in ["ema_short", "ema_medium", "ema_long"]:
            assert col in result.columns
        # EMA should have values after warmup period
        assert result["ema_short"].dropna().shape[0] > 300
        assert result["ema_long"].dropna().shape[0] > 100

    def test_ema_ordering(self, ohlcv_350: pd.DataFrame) -> None:
        """EMA short should be more responsive (closer to price) than long."""
        result = compute_indicators(ohlcv_350)
        # Short EMA should have smaller deviation from close on average
        short_dev = (result["ema_short"] - result["close"]).dropna().abs().mean()
        long_dev = (result["ema_long"] - result["close"]).dropna().abs().mean()
        assert short_dev < long_dev

    def test_bollinger_bands(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        valid = result.dropna(subset=["bb_upper", "bb_lower", "bb_mid"])
        assert len(valid) > 300
        # Upper > Mid > Lower
        assert (valid["bb_upper"] >= valid["bb_mid"]).all()
        assert (valid["bb_mid"] >= valid["bb_lower"]).all()
        # bb_pct should be between 0 and 1 for most bars
        bb_pct_valid = valid["bb_pct"].dropna()
        assert bb_pct_valid.between(-0.5, 1.5).mean() > 0.9

    def test_rsi_range(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        rsi_valid = result["rsi"].dropna()
        assert len(rsi_valid) > 300
        assert rsi_valid.min() >= 0.0
        assert rsi_valid.max() <= 100.0

    def test_macd_components(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        for col in ["macd", "macd_signal", "macd_hist"]:
            assert col in result.columns
        valid = result.dropna(subset=["macd", "macd_signal", "macd_hist"])
        assert len(valid) > 300
        # macd_hist should be macd - macd_signal (approximately)
        expected_hist = valid["macd"] - valid["macd_signal"]
        np.testing.assert_allclose(
            valid["macd_hist"].values, expected_hist.values, atol=1e-6
        )

    def test_atr_positive(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        atr_valid = result["atr"].dropna()
        assert len(atr_valid) > 300
        assert (atr_valid > 0).all()
        # atr_pct should be a small fraction of price
        atr_pct_valid = result["atr_pct"].dropna()
        assert atr_pct_valid.mean() < 0.1  # Less than 10%

    def test_adx_range(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        adx_valid = result["adx"].dropna()
        assert len(adx_valid) > 300
        assert adx_valid.min() >= 0.0
        assert adx_valid.max() <= 100.0

    def test_volume_indicators(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        assert "obv" in result.columns
        assert "volume_ma" in result.columns
        assert "cmf" in result.columns
        # CMF should be between -1 and 1
        cmf_valid = result["cmf"].dropna()
        assert cmf_valid.between(-1.0, 1.0).all()

    def test_custom_config(self, ohlcv_350: pd.DataFrame) -> None:
        config = IndicatorConfig(ema_short=10, rsi_period=7, atr_period=7)
        result = compute_indicators(ohlcv_350, config)
        # Should still produce valid output
        assert result["ema_short"].dropna().shape[0] > 300
        assert result["rsi"].dropna().shape[0] > 300

    def test_stochrsi_range(self, ohlcv_350: pd.DataFrame) -> None:
        result = compute_indicators(ohlcv_350)
        for col in ["stochrsi_k", "stochrsi_d"]:
            valid = result[col].dropna()
            assert len(valid) > 200
            assert valid.min() >= 0.0
            assert valid.max() <= 100.0


class TestZScore:
    """Test z_score() function."""

    def test_mean_near_zero(self) -> None:
        np.random.seed(42)
        series = pd.Series(np.random.normal(100, 10, 500))
        result = z_score(series, lookback=100)
        # After warmup, mean should be near 0
        assert abs(result.iloc[200:].mean()) < 0.5

    def test_std_near_one(self) -> None:
        np.random.seed(42)
        series = pd.Series(np.random.normal(100, 10, 500))
        result = z_score(series, lookback=100)
        # After warmup, std should be near 1
        assert 0.5 < result.iloc[200:].std() < 1.5

    def test_constant_series_returns_zero(self) -> None:
        series = pd.Series([42.0] * 200)
        result = z_score(series, lookback=50)
        # Constant series -> std=0 -> z=0
        assert (result.dropna() == 0.0).all()

    def test_short_lookback(self) -> None:
        np.random.seed(42)
        series = pd.Series(np.random.normal(0, 1, 100))
        result = z_score(series, lookback=20)
        assert len(result.dropna()) > 80


class TestZToScore:
    """Test z_to_score() function."""

    def test_tanh_bounds(self) -> None:
        assert -1.0 <= z_to_score(5.0) <= 1.0
        assert -1.0 <= z_to_score(-5.0) <= 1.0
        assert abs(z_to_score(0.0)) < 0.01

    def test_tanh_symmetry(self) -> None:
        assert abs(z_to_score(2.0) + z_to_score(-2.0)) < 1e-10

    def test_tanh_known_values(self) -> None:
        # tanh(1) ≈ 0.7616
        assert abs(z_to_score(1.0) - 0.7616) < 0.001

    def test_clip_bounds(self) -> None:
        assert z_to_score(5.0, method="clip") == 1.0
        assert z_to_score(-5.0, method="clip") == -1.0
        assert z_to_score(0.0, method="clip") == 0.0
        assert abs(z_to_score(1.5, method="clip") - 0.5) < 0.01

    def test_series_input(self) -> None:
        series = pd.Series([0.0, 1.0, -1.0, 3.0, -3.0])
        result = z_to_score(series, method="tanh")
        assert isinstance(result, pd.Series)
        assert len(result) == 5
        assert (result.abs() <= 1.0).all()

    def test_invalid_method(self) -> None:
        with pytest.raises(ValueError, match="Unknown method"):
            z_to_score(1.0, method="invalid")


class TestNormalizeIndicators:
    """Test normalize_indicators() function."""

    def test_chain_with_compute_indicators(self, ohlcv_350: pd.DataFrame) -> None:
        """Full pipeline: compute_indicators() + normalize_indicators() should work."""
        indicators = compute_indicators(ohlcv_350)
        normalized = normalize_indicators(indicators)

        # Should have z_* columns
        z_cols = [c for c in normalized.columns if c.startswith("z_")]
        assert len(z_cols) >= 5
        expected_z = ["z_macd_hist", "z_obv_change", "z_roc_5", "z_macd_accel", "z_cmf", "z_atr_pct"]
        for col in expected_z:
            assert col in normalized.columns

    def test_z_scores_bounded(self, ohlcv_350: pd.DataFrame) -> None:
        """All z_* columns should be in [-1, +1] range (tanh output)."""
        indicators = compute_indicators(ohlcv_350)
        normalized = normalize_indicators(indicators)

        z_cols = [c for c in normalized.columns if c.startswith("z_")]
        for col in z_cols:
            valid = normalized[col].dropna()
            if len(valid) > 0:
                assert valid.min() >= -1.0, f"{col} min={valid.min()}"
                assert valid.max() <= 1.0, f"{col} max={valid.max()}"

    def test_returns_new_dataframe(self, ohlcv_350: pd.DataFrame) -> None:
        indicators = compute_indicators(ohlcv_350)
        normalized = normalize_indicators(indicators)
        assert normalized is not indicators

    def test_custom_lookback(self, ohlcv_350: pd.DataFrame) -> None:
        indicators = compute_indicators(ohlcv_350)
        normalized = normalize_indicators(indicators, lookback=50)
        z_cols = [c for c in normalized.columns if c.startswith("z_")]
        assert len(z_cols) >= 5

    def test_no_error_on_350_bars(self, ohlcv_350: pd.DataFrame) -> None:
        """S0 completion criteria: 350 bars should run without error."""
        indicators = compute_indicators(ohlcv_350)
        normalized = normalize_indicators(indicators)
        # Should have data in the last 100 rows
        last_100 = normalized.tail(100)
        z_cols = [c for c in last_100.columns if c.startswith("z_")]
        for col in z_cols:
            assert last_100[col].notna().sum() > 90, f"{col} has too many NaNs in last 100 bars"
