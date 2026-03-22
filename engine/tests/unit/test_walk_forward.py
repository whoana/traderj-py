"""Tests for walk-forward backtesting."""

from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from engine.strategy.backtest.walk_forward import (
    WalkForwardConfig,
    WalkForwardEngine,
    WalkForwardResult,
)
from engine.strategy.signal import SignalGenerator
from shared.enums import EntryMode, ScoringMode


def _make_ohlcv(n_bars: int = 800, base_price: float = 90_000_000.0) -> pd.DataFrame:
    """Create synthetic OHLCV data with trend/range cycles."""
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1h", tz=UTC)
    price = base_price
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}

    for i in range(n_bars):
        change = (i % 7 - 3) * 0.002 + 0.0005
        price = price * (1 + change)
        data["open"].append(price)
        data["high"].append(price * 1.005)
        data["low"].append(price * 0.995)
        data["close"].append(price)
        data["volume"].append(1000 + (i % 50) * 20)

    return pd.DataFrame(data, index=dates)


def _make_signal_gen() -> SignalGenerator:
    return SignalGenerator(
        strategy_id="TEST",
        scoring_mode=ScoringMode.TREND_FOLLOW,
        entry_mode=EntryMode.WEIGHTED,
        tf_weights={"1h": 1.0},
        buy_threshold=0.10,
        sell_threshold=-0.10,
    )


class TestWalkForwardBasic:
    def test_runs_with_sufficient_data(self):
        df = _make_ohlcv(800)
        engine = WalkForwardEngine(
            signal_generator=_make_signal_gen(),
            wf_config=WalkForwardConfig(is_bars=300, oos_bars=100, step_size=100),
        )
        result = engine.run({"1h": df})

        assert isinstance(result, WalkForwardResult)
        assert len(result.windows) > 0

    def test_insufficient_data_raises(self):
        df = _make_ohlcv(100)
        engine = WalkForwardEngine(
            signal_generator=_make_signal_gen(),
            wf_config=WalkForwardConfig(is_bars=300, oos_bars=100),
        )
        with pytest.raises(ValueError, match="Need at least"):
            engine.run({"1h": df})

    def test_missing_primary_tf_raises(self):
        df = _make_ohlcv(800)
        engine = WalkForwardEngine(signal_generator=_make_signal_gen())
        with pytest.raises(ValueError, match="No data"):
            engine.run({"4h": df}, primary_tf="1h")


class TestWalkForwardWindows:
    def test_correct_window_count(self):
        df = _make_ohlcv(800)
        engine = WalkForwardEngine(
            signal_generator=_make_signal_gen(),
            wf_config=WalkForwardConfig(is_bars=300, oos_bars=100, step_size=100),
        )
        result = engine.run({"1h": df})

        # Window 0: IS=[0:300], OOS=[300:400]
        # Window 1: IS=[100:400], OOS=[400:500]
        # Window 2: IS=[200:500], OOS=[500:600]
        # Window 3: IS=[300:600], OOS=[600:700]
        # Window 4: IS=[400:700], OOS=[700:800]
        assert len(result.windows) == 5

    def test_window_ranges_correct(self):
        df = _make_ohlcv(800)
        engine = WalkForwardEngine(
            signal_generator=_make_signal_gen(),
            wf_config=WalkForwardConfig(is_bars=300, oos_bars=100, step_size=100),
        )
        result = engine.run({"1h": df})

        w0 = result.windows[0]
        assert w0.is_start_idx == 0
        assert w0.is_end_idx == 300
        assert w0.oos_start_idx == 300
        assert w0.oos_end_idx == 400

        w1 = result.windows[1]
        assert w1.is_start_idx == 100
        assert w1.oos_start_idx == 400


class TestWalkForwardMetrics:
    def test_aggregate_metrics_present(self):
        df = _make_ohlcv(800)
        engine = WalkForwardEngine(
            signal_generator=_make_signal_gen(),
            wf_config=WalkForwardConfig(is_bars=300, oos_bars=100, step_size=100),
        )
        result = engine.run({"1h": df})

        agg = result.aggregate_metrics
        assert "wf_total_windows" in agg
        assert "wf_valid_windows" in agg

    def test_to_json_serializable(self):
        df = _make_ohlcv(800)
        engine = WalkForwardEngine(
            signal_generator=_make_signal_gen(),
            wf_config=WalkForwardConfig(is_bars=300, oos_bars=100, step_size=100),
        )
        result = engine.run({"1h": df})
        json_out = result.to_json()

        assert "config" in json_out
        assert "windows" in json_out
        assert "aggregate_metrics" in json_out
        assert isinstance(json_out["windows"], list)

    def test_total_oos_trades_property(self):
        df = _make_ohlcv(800)
        engine = WalkForwardEngine(
            signal_generator=_make_signal_gen(),
            wf_config=WalkForwardConfig(is_bars=300, oos_bars=100, step_size=100),
        )
        result = engine.run({"1h": df})

        total = result.total_oos_trades
        manual_total = sum(len(w.oos_result.trades) for w in result.valid_windows)
        assert total == manual_total
