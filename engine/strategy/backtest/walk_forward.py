"""Walk-forward backtesting for Out-of-Sample validation.

Splits data into rolling windows of in-sample (training) + out-of-sample (test):
  - Train on IS window, run backtest on OOS window
  - Roll forward by step_size, repeat
  - Aggregate OOS results for unbiased performance estimate

Example with 1000 bars, is_size=500, oos_size=100, step_size=100:
  Window 1: IS=[0:500],   OOS=[500:600]
  Window 2: IS=[100:600], OOS=[600:700]
  Window 3: IS=[200:700], OOS=[700:800]
  ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from engine.strategy.backtest.engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
    BacktestTrade,
)
from engine.strategy.backtest.metrics import compute_metrics
from engine.strategy.risk import RiskConfig
from engine.strategy.signal import SignalGenerator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardConfig:
    """Walk-forward parameters."""

    is_bars: int = 500          # in-sample window size (bars)
    oos_bars: int = 100         # out-of-sample window size (bars)
    step_size: int = 100        # roll step size (bars)
    min_trades_per_window: int = 3  # minimum trades for valid OOS window


@dataclass
class WalkForwardWindow:
    """A single walk-forward window result."""

    window_id: int
    is_start_idx: int
    is_end_idx: int
    oos_start_idx: int
    oos_end_idx: int
    oos_result: BacktestResult
    is_valid: bool = True


@dataclass
class WalkForwardResult:
    """Aggregate walk-forward results."""

    windows: list[WalkForwardWindow]
    aggregate_metrics: dict[str, Any]
    config: dict[str, Any]

    @property
    def valid_windows(self) -> list[WalkForwardWindow]:
        return [w for w in self.windows if w.is_valid]

    @property
    def total_oos_trades(self) -> int:
        return sum(
            len(w.oos_result.trades) for w in self.valid_windows
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "total_windows": len(self.windows),
            "valid_windows": len(self.valid_windows),
            "total_oos_trades": self.total_oos_trades,
            "aggregate_metrics": self.aggregate_metrics,
            "windows": [
                {
                    "window_id": w.window_id,
                    "is_range": [w.is_start_idx, w.is_end_idx],
                    "oos_range": [w.oos_start_idx, w.oos_end_idx],
                    "oos_trades": len(w.oos_result.trades),
                    "oos_metrics": w.oos_result.metrics,
                    "is_valid": w.is_valid,
                }
                for w in self.windows
            ],
        }


class WalkForwardEngine:
    """Walk-forward backtesting engine."""

    def __init__(
        self,
        signal_generator: SignalGenerator,
        risk_config: RiskConfig | None = None,
        backtest_config: BacktestConfig | None = None,
        wf_config: WalkForwardConfig | None = None,
    ) -> None:
        self.signal_gen = signal_generator
        self.risk_config = risk_config or RiskConfig()
        self.bt_config = backtest_config or BacktestConfig()
        self.wf_config = wf_config or WalkForwardConfig()

    def run(
        self,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        primary_tf: str = "1h",
        macro_scores: pd.Series | None = None,
    ) -> WalkForwardResult:
        """Run walk-forward analysis.

        Args:
            ohlcv_by_tf: Full historical data by timeframe.
            primary_tf: Primary timeframe for bar iteration.
            macro_scores: Optional macro scores.

        Returns:
            WalkForwardResult with per-window and aggregate metrics.
        """
        primary_df = ohlcv_by_tf.get(primary_tf)
        if primary_df is None:
            raise ValueError(f"No data for primary timeframe {primary_tf}")

        total_bars = len(primary_df)
        cfg = self.wf_config
        min_required = cfg.is_bars + cfg.oos_bars

        if total_bars < min_required:
            raise ValueError(
                f"Need at least {min_required} bars, got {total_bars}"
            )

        windows: list[WalkForwardWindow] = []
        window_id = 0

        is_start = 0
        while True:
            is_end = is_start + cfg.is_bars
            oos_start = is_end
            oos_end = oos_start + cfg.oos_bars

            if oos_end > total_bars:
                break

            # Slice data for OOS window
            oos_data = self._slice_data(ohlcv_by_tf, oos_start, oos_end)
            oos_macro = None
            if macro_scores is not None:
                oos_idx = primary_df.index[oos_start:oos_end]
                oos_macro = macro_scores.reindex(oos_idx)

            # Run backtest on OOS data
            bt_engine = BacktestEngine(
                signal_generator=self.signal_gen,
                risk_config=self.risk_config,
                config=self.bt_config,
            )

            try:
                oos_result = bt_engine.run(
                    ohlcv_by_tf=oos_data,
                    macro_scores=oos_macro,
                    primary_tf=primary_tf,
                )
                is_valid = len(oos_result.trades) >= cfg.min_trades_per_window
            except Exception:
                logger.warning("Window %d OOS backtest failed", window_id)
                oos_result = BacktestResult(
                    strategy_id=self.signal_gen.strategy_id,
                    config={},
                    trades=[],
                    equity_curve=[],
                    metrics={},
                )
                is_valid = False

            windows.append(WalkForwardWindow(
                window_id=window_id,
                is_start_idx=is_start,
                is_end_idx=is_end,
                oos_start_idx=oos_start,
                oos_end_idx=oos_end,
                oos_result=oos_result,
                is_valid=is_valid,
            ))

            window_id += 1
            is_start += cfg.step_size

        # Aggregate OOS metrics
        aggregate = self._aggregate_results(windows)

        return WalkForwardResult(
            windows=windows,
            aggregate_metrics=aggregate,
            config={
                "is_bars": cfg.is_bars,
                "oos_bars": cfg.oos_bars,
                "step_size": cfg.step_size,
                "total_bars": total_bars,
                "total_windows": len(windows),
                "valid_windows": sum(1 for w in windows if w.is_valid),
            },
        )

    def _slice_data(
        self,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        start_idx: int,
        end_idx: int,
    ) -> dict[str, pd.DataFrame]:
        """Slice all timeframe data to the OOS window.

        For higher timeframes, includes all bars up to the OOS end
        to provide sufficient look-back for indicator calculation.
        """
        result: dict[str, pd.DataFrame] = {}
        for tf, df in ohlcv_by_tf.items():
            # Include data from start (for indicator warmup) through end
            result[tf] = df.iloc[:end_idx].copy()
        return result

    @staticmethod
    def _aggregate_results(windows: list[WalkForwardWindow]) -> dict[str, Any]:
        """Aggregate OOS results across all valid windows."""
        valid = [w for w in windows if w.is_valid]
        if not valid:
            return {"error": "no_valid_windows"}

        all_trades: list[BacktestTrade] = []
        all_equity: list[dict] = []
        initial_balance = 50_000_000.0

        for w in valid:
            all_trades.extend(w.oos_result.trades)
            all_equity.extend(w.oos_result.equity_curve)
            if w.oos_result.config.get("initial_balance"):
                initial_balance = w.oos_result.config["initial_balance"]

        # Per-window metrics for consistency analysis
        window_returns = []
        window_sharpes = []
        window_win_rates = []

        for w in valid:
            m = w.oos_result.metrics
            if m:
                window_returns.append(m.get("total_return_pct", 0))
                window_sharpes.append(m.get("sharpe_ratio", 0))
                window_win_rates.append(m.get("win_rate_pct", 0))

        aggregate = compute_metrics(
            trades=all_trades,
            equity_curve=all_equity,
            initial_balance=initial_balance,
        )

        # Add walk-forward specific metrics
        aggregate["wf_total_windows"] = len(windows)
        aggregate["wf_valid_windows"] = len(valid)
        aggregate["wf_total_oos_trades"] = len(all_trades)

        if window_returns:
            aggregate["wf_avg_window_return_pct"] = round(
                sum(window_returns) / len(window_returns), 2
            )
            aggregate["wf_positive_windows"] = sum(1 for r in window_returns if r > 0)
            aggregate["wf_positive_window_rate_pct"] = round(
                aggregate["wf_positive_windows"] / len(window_returns) * 100, 1
            )

        if window_sharpes:
            aggregate["wf_avg_window_sharpe"] = round(
                sum(window_sharpes) / len(window_sharpes), 2
            )

        if window_win_rates:
            aggregate["wf_avg_window_win_rate"] = round(
                sum(window_win_rates) / len(window_win_rates), 1
            )

        return aggregate
