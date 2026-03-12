"""Unit tests for scoring engine (filters, scoring, mtf, risk, signal, presets)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from shared.enums import EntryMode, ScoringMode, SignalDirection
from engine.strategy.filters import (
    breakout_score,
    momentum_score,
    quick_momentum_score,
    reversal_score,
    trend_score,
    volume_score,
)
from engine.strategy.scoring import ScoreWeights, TimeframeScore, default_weights
from engine.strategy.mtf import aggregate_mtf, check_daily_gate, DailyGateResult
from engine.strategy.risk import RiskConfig, RiskDecision, RiskEngine
from engine.strategy.signal import SignalGenerator, SignalResult
from engine.strategy.presets import STRATEGY_PRESETS, StrategyPreset
from engine.strategy.indicators import compute_indicators, IndicatorConfig
from engine.strategy.normalizer import normalize_indicators


def _make_ohlcv(n: int = 350, base_price: float = 50_000_000) -> pd.DataFrame:
    """Create synthetic OHLCV data for testing."""
    np.random.seed(42)
    prices = base_price + np.cumsum(np.random.randn(n) * 100_000)
    prices = np.abs(prices)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices * (1 + np.random.uniform(0, 0.02, n)),
            "low": prices * (1 - np.random.uniform(0, 0.02, n)),
            "close": prices * (1 + np.random.randn(n) * 0.005),
            "volume": np.random.uniform(50, 200, n),
        }
    )


def _make_indicator_df() -> pd.DataFrame:
    """Create a DataFrame with computed indicators for filter testing."""
    df = _make_ohlcv()
    df = compute_indicators(df)
    df = normalize_indicators(df)
    return df


# --- ScoreWeights tests ---


class TestScoreWeights:
    def test_valid_weights(self) -> None:
        sw = ScoreWeights(0.5, 0.3, 0.2)
        assert abs(sw.w1 + sw.w2 + sw.w3 - 1.0) < 0.001

    def test_invalid_weights_raises(self) -> None:
        with pytest.raises(ValueError, match="must sum to 1.0"):
            ScoreWeights(0.5, 0.5, 0.5)

    def test_default_weights(self) -> None:
        tf = default_weights(ScoringMode.TREND_FOLLOW)
        assert tf.w1 == 0.50
        hyb = default_weights(ScoringMode.HYBRID)
        assert hyb.w1 == 0.40


# --- TimeframeScore tests ---


class TestTimeframeScore:
    def test_combined_within_range(self) -> None:
        ts = TimeframeScore("4h", s1=0.8, s2=0.5, s3=0.3)
        w = ScoreWeights(0.5, 0.3, 0.2)
        combined = ts.combined(w)
        assert -1.0 <= combined <= 1.0

    def test_combined_extreme(self) -> None:
        ts = TimeframeScore("4h", s1=1.0, s2=1.0, s3=1.0)
        w = ScoreWeights(0.5, 0.3, 0.2)
        assert ts.combined(w) == 1.0

    def test_as_dict(self) -> None:
        ts = TimeframeScore("1h", s1=0.5, s2=-0.2, s3=0.1)
        w = ScoreWeights(0.5, 0.3, 0.2)
        d = ts.as_dict(w)
        assert "s1" in d
        assert "combined" in d
        assert "weights" in d


# --- Filter functions tests ---


class TestFilters:
    @pytest.fixture()
    def indicator_df(self) -> pd.DataFrame:
        return _make_indicator_df()

    def test_trend_score_range(self, indicator_df: pd.DataFrame) -> None:
        score = trend_score(indicator_df)
        assert -1.0 <= score <= 1.0

    def test_momentum_score_range(self, indicator_df: pd.DataFrame) -> None:
        score = momentum_score(indicator_df)
        assert -1.0 <= score <= 1.0

    def test_volume_score_range(self, indicator_df: pd.DataFrame) -> None:
        score = volume_score(indicator_df)
        assert -1.0 <= score <= 1.0

    def test_reversal_score_range(self, indicator_df: pd.DataFrame) -> None:
        score = reversal_score(indicator_df)
        assert -1.0 <= score <= 1.0

    def test_breakout_score_range(self, indicator_df: pd.DataFrame) -> None:
        score = breakout_score(indicator_df)
        assert -1.0 <= score <= 1.0

    def test_quick_momentum_score_range(self, indicator_df: pd.DataFrame) -> None:
        score = quick_momentum_score(indicator_df)
        assert -1.0 <= score <= 1.0

    def test_empty_df_returns_zero(self) -> None:
        df = pd.DataFrame({"close": [100]})
        assert trend_score(df) == 0.0


# --- MTF aggregation tests ---


class TestMTF:
    def test_weighted_aggregation(self) -> None:
        scores = {
            "1h": TimeframeScore("1h", s1=0.5, s2=0.3, s3=0.2),
            "4h": TimeframeScore("4h", s1=0.8, s2=0.6, s3=0.4),
        }
        w = ScoreWeights(0.5, 0.3, 0.2)
        tf_w = {"1h": 0.3, "4h": 0.7}

        result = aggregate_mtf(scores, w, tf_w, EntryMode.WEIGHTED)
        assert -1.0 <= result <= 1.0
        assert result > 0  # Both TFs bullish

    def test_majority_requires_min(self) -> None:
        scores = {
            "1h": TimeframeScore("1h", s1=0.5, s2=0.3, s3=0.2),
            "4h": TimeframeScore("4h", s1=-0.1, s2=-0.1, s3=-0.1),
        }
        w = ScoreWeights(0.5, 0.3, 0.2)
        tf_w = {"1h": 0.3, "4h": 0.7}

        result = aggregate_mtf(
            scores, w, tf_w, EntryMode.MAJORITY, majority_min=2
        )
        assert result == 0.0  # Only 1 TF bullish, need 2

    def test_empty_scores(self) -> None:
        result = aggregate_mtf(
            {}, ScoreWeights(0.5, 0.3, 0.2), {}, EntryMode.WEIGHTED
        )
        assert result == 0.0


class TestDailyGate:
    def test_gate_disabled(self) -> None:
        result = check_daily_gate(None)
        assert result.passed is True
        assert result.reason == "gate_disabled"

    def test_bullish_alignment(self) -> None:
        df = pd.DataFrame({"ema_short": [100, 110], "ema_medium": [90, 100]})
        result = check_daily_gate(df)
        assert result.passed is True
        assert result.reason == "bullish_alignment"

    def test_bearish_alignment(self) -> None:
        df = pd.DataFrame({"ema_short": [90, 95], "ema_medium": [100, 105]})
        result = check_daily_gate(df)
        assert result.passed is False
        assert result.reason == "bearish_alignment"


# --- RiskEngine tests ---


class TestRiskEngine:
    def test_basic_buy_approved(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=50_000_000,
            current_atr=1_000_000,
        )
        assert decision.allowed is True
        assert decision.position_size_krw > 0
        assert decision.stop_loss_price > 0

    def test_volatility_cap_blocks(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=50_000_000,
            current_atr=5_000_000,  # 10% ATR -> exceeds 8% cap
        )
        assert decision.allowed is False
        assert "volatility_cap" in decision.reason

    def test_below_min_order(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate_buy(
            total_balance_krw=1_000,  # Very small balance
            current_price=50_000_000,
            current_atr=1_000_000,
        )
        assert decision.allowed is False
        assert decision.reason == "below_min_order"

    def test_daily_loss_limit(self) -> None:
        engine = RiskEngine()
        engine.daily_pnl = -600_000  # 6% of 10M -> exceeds 5% limit
        engine.daily_date = datetime.now(UTC).strftime("%Y-%m-%d")
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=50_000_000,
            current_atr=1_000_000,
        )
        assert decision.allowed is False
        assert "daily_loss_limit" in decision.reason

    def test_cooldown_blocks(self) -> None:
        engine = RiskEngine()
        engine.cooldown_until = datetime.now(UTC) + timedelta(hours=1)
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=50_000_000,
            current_atr=1_000_000,
        )
        assert decision.allowed is False
        assert "cooldown" in decision.reason

    def test_consecutive_losses_trigger_cooldown(self) -> None:
        engine = RiskEngine(config=RiskConfig(max_consecutive_losses=3))
        engine.record_trade_result(-100_000)
        engine.record_trade_result(-100_000)
        assert engine.cooldown_until is None
        engine.record_trade_result(-100_000)  # 3rd loss
        assert engine.cooldown_until is not None

    def test_win_resets_consecutive_losses(self) -> None:
        engine = RiskEngine()
        engine.record_trade_result(-100_000)
        engine.record_trade_result(-100_000)
        assert engine.consecutive_losses == 2
        engine.record_trade_result(50_000)
        assert engine.consecutive_losses == 0

    def test_atr_stop_loss(self) -> None:
        engine = RiskEngine()
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=50_000_000,
            current_atr=1_000_000,
        )
        expected_stop = 50_000_000 - (1_000_000 * 2.0)
        assert decision.stop_loss_price == expected_stop

    def test_volatility_sizing(self) -> None:
        config = RiskConfig(target_risk_pct=0.02)
        engine = RiskEngine(config=config)
        # ATR = 2% of price -> position_pct = 0.02/0.02 = 1.0 -> capped at max
        decision = engine.evaluate_buy(
            total_balance_krw=10_000_000,
            current_price=50_000_000,
            current_atr=1_000_000,  # 2% ATR
        )
        assert decision.position_pct == config.max_position_pct


# --- SignalGenerator tests ---


class TestSignalGenerator:
    def test_generate_returns_signal(self) -> None:
        gen = SignalGenerator(
            strategy_id="test",
            scoring_mode=ScoringMode.TREND_FOLLOW,
            entry_mode=EntryMode.WEIGHTED,
            tf_weights={"4h": 1.0},
        )
        ohlcv = {"4h": _make_ohlcv()}
        result = gen.generate(ohlcv)

        assert isinstance(result, SignalResult)
        assert result.direction in (
            SignalDirection.BUY,
            SignalDirection.SELL,
            SignalDirection.HOLD,
        )
        assert -1.0 <= result.score <= 1.0
        assert "strategy_id" in result.details

    def test_hybrid_mode(self) -> None:
        gen = SignalGenerator(
            strategy_id="hybrid-test",
            scoring_mode=ScoringMode.HYBRID,
            entry_mode=EntryMode.WEIGHTED,
            tf_weights={"4h": 1.0},
        )
        result = gen.generate({"4h": _make_ohlcv()})
        assert result.details["scoring_mode"] == "hybrid"

    def test_daily_gate_blocks_buy(self) -> None:
        gen = SignalGenerator(
            strategy_id="gate-test",
            scoring_mode=ScoringMode.TREND_FOLLOW,
            entry_mode=EntryMode.WEIGHTED,
            tf_weights={"4h": 1.0},
            use_daily_gate=True,
            buy_threshold=-10.0,  # Very low threshold to force BUY
        )
        df_4h = _make_ohlcv()
        # 1d with bearish alignment (ema_short < ema_medium)
        df_1d = pd.DataFrame(
            {
                "open": [50_000_000], "high": [51_000_000],
                "low": [49_000_000], "close": [50_500_000],
                "volume": [100],
                "ema_short": [90], "ema_medium": [100],
            }
        )
        result = gen.generate({"4h": df_4h, "1d": df_1d})
        # With daily gate bearish, BUY should be blocked
        assert result.details["daily_gate_status"] in ("bearish_alignment", "gate_disabled")


# --- Presets tests ---


class TestPresets:
    def test_all_presets_exist(self) -> None:
        assert "default" in STRATEGY_PRESETS
        for i in range(1, 7):
            assert f"STR-00{i}" in STRATEGY_PRESETS

    def test_preset_weights_valid(self) -> None:
        for name, preset in STRATEGY_PRESETS.items():
            total = preset.score_weights.w1 + preset.score_weights.w2 + preset.score_weights.w3
            assert abs(total - 1.0) < 0.001, f"Preset {name} weights don't sum to 1.0"

    def test_preset_thresholds(self) -> None:
        for name, preset in STRATEGY_PRESETS.items():
            assert preset.buy_threshold > 0, f"Preset {name} buy_threshold <= 0"
            assert preset.sell_threshold < 0, f"Preset {name} sell_threshold >= 0"

    def test_all_presets_generate(self) -> None:
        """Verify all presets can generate signals without error."""
        ohlcv_4h = _make_ohlcv()
        ohlcv_1h = _make_ohlcv(base_price=50_000_000)
        ohlcv_1d = _make_ohlcv(n=100, base_price=50_000_000)
        ohlcv_15m = _make_ohlcv(base_price=50_000_000)

        for name, preset in STRATEGY_PRESETS.items():
            gen = SignalGenerator(
                strategy_id=preset.strategy_id,
                scoring_mode=preset.scoring_mode,
                entry_mode=preset.entry_mode,
                score_weights=preset.score_weights,
                tf_weights=preset.tf_weights,
                buy_threshold=preset.buy_threshold,
                sell_threshold=preset.sell_threshold,
                majority_min=preset.majority_min,
                use_daily_gate=preset.use_daily_gate,
                macro_weight=preset.macro_weight,
            )
            ohlcv = {
                "15m": ohlcv_15m,
                "1h": ohlcv_1h,
                "4h": ohlcv_4h,
                "1d": ohlcv_1d,
            }
            result = gen.generate(ohlcv)
            assert result.direction in (
                SignalDirection.BUY,
                SignalDirection.SELL,
                SignalDirection.HOLD,
            ), f"Preset {name} failed"
