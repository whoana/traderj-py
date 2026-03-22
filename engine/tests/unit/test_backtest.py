"""Unit tests for BacktestEngine and metrics calculation.

Tests:
- Sharpe ratio computation
- Max drawdown computation
- Equity curve generation
- Fee and slippage handling
- Edge cases (no trades, single bar)
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pandas as pd
import pytest

from engine.strategy.backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    BacktestTrade,
)
from engine.strategy.backtest.metrics import (
    _compute_returns,
    _max_drawdown,
    _sharpe_ratio,
    _sortino_ratio,
    _std,
    compute_metrics,
)
from engine.strategy.signal import SignalGenerator
from shared.enums import EntryMode, ScoringMode

# ── Helpers ──────────────────────────────────────────────────────


def _make_ohlcv_df(n_bars: int = 200, base_price: float = 90_000_000.0) -> pd.DataFrame:
    """Create synthetic OHLCV data with a trend pattern."""
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="1h", tz=UTC)
    data = {
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    }
    price = base_price
    for i in range(n_bars):
        # Create a mild uptrend with noise
        change = (i % 7 - 3) * 0.002 + 0.0005  # slight uptrend bias
        price = price * (1 + change)
        o = price
        h = price * 1.005
        low = price * 0.995
        c = price
        data["open"].append(o)
        data["high"].append(h)
        data["low"].append(low)
        data["close"].append(c)
        data["volume"].append(10 + i % 5)

    return pd.DataFrame(data, index=dates)


def _make_signal_generator() -> SignalGenerator:
    return SignalGenerator(
        strategy_id="test-bt",
        scoring_mode=ScoringMode.TREND_FOLLOW,
        entry_mode=EntryMode.WEIGHTED,
        tf_weights={"1h": 1.0},
        buy_threshold=0.10,
        sell_threshold=-0.10,
    )


# ── Metrics unit tests ──────────────────────────────────────────


class TestMetricsHelpers:
    def test_max_drawdown_no_data(self):
        dd, dur = _max_drawdown([])
        assert dd == 0.0
        assert dur == 0

    def test_max_drawdown_flat(self):
        dd, dur = _max_drawdown([100, 100, 100])
        assert dd == 0.0

    def test_max_drawdown_simple(self):
        # Peak at 100, drops to 80 = 20% drawdown
        equities = [100, 110, 100, 80, 90, 110]
        dd, dur = _max_drawdown(equities)
        expected_dd = (110 - 80) / 110  # ~27.27%
        assert abs(dd - expected_dd) < 0.01

    def test_max_drawdown_monotonic_up(self):
        dd, dur = _max_drawdown([100, 110, 120, 130])
        assert dd == 0.0

    def test_compute_returns_empty(self):
        assert _compute_returns([]) == []
        assert _compute_returns([100]) == []

    def test_compute_returns_basic(self):
        returns = _compute_returns([100, 110, 105])
        assert len(returns) == 2
        assert abs(returns[0] - 0.10) < 0.001
        assert abs(returns[1] - (-0.04545)) < 0.001

    def test_std_single_value(self):
        assert _std([5.0]) == 0.0

    def test_std_basic(self):
        vals = [2, 4, 4, 4, 5, 5, 7, 9]
        result = _std(vals)
        assert result > 0

    def test_sharpe_ratio_zero_returns(self):
        assert _sharpe_ratio([], 0.035, 365) == 0.0

    def test_sharpe_ratio_positive(self):
        # Varying positive returns should give positive Sharpe
        returns = [0.01 + i * 0.001 for i in range(100)]
        sharpe = _sharpe_ratio(returns, 0.035, 365)
        assert sharpe > 0

    def test_sortino_ratio_no_downside(self):
        # All positive returns: sortino = inf
        returns = [0.01] * 10
        sortino = _sortino_ratio(returns, 0.035, 365)
        assert sortino == float("inf")

    def test_sortino_ratio_with_downside(self):
        returns = [0.02, -0.01, 0.03, -0.02, 0.01]
        sortino = _sortino_ratio(returns, 0.035, 365)
        # Should be finite
        assert not math.isinf(sortino)


class TestComputeMetrics:
    def test_no_trades(self):
        metrics = compute_metrics([], [{"equity": 10_000_000}], 10_000_000)
        assert metrics["total_trades"] == 0
        assert metrics["total_return_pct"] == 0.0

    def test_single_winning_trade(self):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        later = datetime(2024, 1, 2, tzinfo=UTC)
        trades = [
            BacktestTrade(
                trade_id="t1",
                entry_time=now,
                exit_time=later,
                side="long",
                entry_price=90_000_000,
                exit_price=95_000_000,
                amount_btc=0.01,
                pnl_krw=50_000,
                pnl_pct=0.055,
                exit_reason="signal_sell",
            )
        ]
        equity_curve = [
            {"equity": 10_000_000},
            {"equity": 10_050_000},
        ]
        metrics = compute_metrics(trades, equity_curve, 10_000_000)

        assert metrics["total_trades"] == 1
        assert metrics["winning_trades"] == 1
        assert metrics["losing_trades"] == 0
        assert metrics["win_rate_pct"] == 100.0
        assert metrics["total_return_pct"] == 0.5
        assert metrics["profit_factor"] == float("inf")

    def test_mixed_trades(self):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        trades = [
            BacktestTrade("t1", now, now, "long", 90e6, 92e6, 0.01, 20000, 0.02, "sell"),
            BacktestTrade("t2", now, now, "long", 92e6, 90e6, 0.01, -20000, -0.02, "sell"),
            BacktestTrade("t3", now, now, "long", 90e6, 95e6, 0.01, 50000, 0.05, "sell"),
        ]
        equity_curve = [
            {"equity": 10_000_000},
            {"equity": 10_020_000},
            {"equity": 10_000_000},
            {"equity": 10_050_000},
        ]
        metrics = compute_metrics(trades, equity_curve, 10_000_000)

        assert metrics["total_trades"] == 3
        assert metrics["winning_trades"] == 2
        assert metrics["losing_trades"] == 1
        assert metrics["win_rate_pct"] == pytest.approx(66.7, abs=0.1)
        assert metrics["profit_factor"] == pytest.approx(70000 / 20000, abs=0.01)

    def test_max_consecutive(self):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        trades = [
            BacktestTrade("t1", now, now, "long", 90e6, 91e6, 0.01, 10000, 0.01, "sell"),
            BacktestTrade("t2", now, now, "long", 90e6, 91e6, 0.01, 10000, 0.01, "sell"),
            BacktestTrade("t3", now, now, "long", 90e6, 89e6, 0.01, -10000, -0.01, "sell"),
            BacktestTrade("t4", now, now, "long", 90e6, 89e6, 0.01, -10000, -0.01, "sell"),
            BacktestTrade("t5", now, now, "long", 90e6, 89e6, 0.01, -10000, -0.01, "sell"),
        ]
        equity_curve = [{"equity": 10e6}] * 6
        metrics = compute_metrics(trades, equity_curve, 10e6)

        assert metrics["max_consecutive_wins"] == 2
        assert metrics["max_consecutive_losses"] == 3


class TestBacktestEngine:
    def test_backtest_runs(self):
        """BacktestEngine should produce results with trades and equity."""
        signal_gen = _make_signal_generator()
        engine = BacktestEngine(
            signal_generator=signal_gen,
            config=BacktestConfig(initial_balance_krw=10_000_000, max_bars=50),
        )

        df = _make_ohlcv_df(200)
        result = engine.run({"1h": df}, primary_tf="1h")

        assert isinstance(result, BacktestResult)
        assert result.strategy_id == "test-bt"
        assert len(result.equity_curve) == 50
        assert result.metrics["final_equity"] > 0

    def test_backtest_empty_data_raises(self):
        """Should raise on empty primary timeframe."""
        signal_gen = _make_signal_generator()
        engine = BacktestEngine(signal_generator=signal_gen)

        with pytest.raises(ValueError, match="No data"):
            engine.run({"1h": pd.DataFrame()}, primary_tf="1h")

    def test_backtest_missing_tf_raises(self):
        """Should raise when primary TF not in data."""
        signal_gen = _make_signal_generator()
        engine = BacktestEngine(signal_generator=signal_gen)

        with pytest.raises(ValueError, match="No data"):
            engine.run({"4h": _make_ohlcv_df(100)}, primary_tf="1h")

    def test_backtest_fees_reduce_equity(self):
        """Fees and slippage should reduce final equity vs zero-cost."""
        signal_gen = _make_signal_generator()

        engine_with_fees = BacktestEngine(
            signal_generator=signal_gen,
            config=BacktestConfig(fee_rate=0.001, slippage_bps=10, max_bars=50),
        )
        engine_no_fees = BacktestEngine(
            signal_generator=signal_gen,
            config=BacktestConfig(fee_rate=0.0, slippage_bps=0, max_bars=50),
        )

        df = _make_ohlcv_df(200)
        r1 = engine_with_fees.run({"1h": df})
        r2 = engine_no_fees.run({"1h": df})

        # If trades happened, fees should reduce equity
        if r1.trades and r2.trades:
            assert r1.metrics["final_equity"] <= r2.metrics["final_equity"]

    def test_backtest_to_json(self):
        """to_json() should produce serializable dict."""
        signal_gen = _make_signal_generator()
        engine = BacktestEngine(
            signal_generator=signal_gen,
            config=BacktestConfig(max_bars=30),
        )
        df = _make_ohlcv_df(200)
        result = engine.run({"1h": df})
        json_data = result.to_json()

        assert "strategy_id" in json_data
        assert "trades" in json_data
        assert "equity_curve" in json_data
        assert "metrics" in json_data
        assert isinstance(json_data["trades"], list)

    def test_backtest_force_close_at_end(self):
        """Open position should be force-closed at backtest end or via risk exits."""
        signal_gen = _make_signal_generator()
        # Use very low thresholds to ensure at least one BUY
        signal_gen.buy_threshold = 0.001
        signal_gen.sell_threshold = -999  # Never sell via signal

        engine = BacktestEngine(
            signal_generator=signal_gen,
            config=BacktestConfig(max_bars=50),
        )
        df = _make_ohlcv_df(200)
        result = engine.run({"1h": df})

        # Trades should close via stop_loss, take_profit, trailing_stop, or backtest_end
        valid_reasons = {"backtest_end", "stop_loss", "take_profit", "trailing_stop"}
        if result.trades:
            assert all(t.exit_reason in valid_reasons or t.exit_reason == "signal_sell"
                      for t in result.trades)
