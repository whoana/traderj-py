"""Gate 1 validation — Walk-forward OOS verification before applying tuned params.

Runs 3-window walk-forward backtest with candidate parameters, then checks
4 gate criteria against baseline metrics. Returns pass/warn/fail verdict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from engine.strategy.backtest.engine import BacktestConfig
from engine.strategy.backtest.walk_forward import (
    WalkForwardConfig,
    WalkForwardEngine,
)
from engine.strategy.presets import StrategyPreset, _apply_overrides
from engine.strategy.signal import SignalGenerator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateCheck:
    """Result of a single gate criterion check."""

    name: str
    value: float
    threshold: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": round(self.value, 2),
            "threshold": round(self.threshold, 2),
            "pass": self.passed,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Gate 1 validation result."""

    windows: list[dict[str, Any]]
    avg_return_pct: float
    avg_pf: float
    avg_mdd: float
    total_trades: int
    gates: dict[str, GateCheck]
    verdict: str  # "pass" | "warn" | "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "windows": self.windows,
            "avg_return_pct": round(self.avg_return_pct, 2),
            "avg_pf": round(self.avg_pf, 2),
            "avg_mdd": round(self.avg_mdd, 2),
            "total_trades": self.total_trades,
            "gates": {k: v.to_dict() for k, v in self.gates.items()},
            "verdict": self.verdict,
        }


# Default gate thresholds
_DEFAULT_OOS_RETURN_MARGIN = 2.0  # baseline + 2%
_DEFAULT_PF_MIN = 1.2
_DEFAULT_MDD_FACTOR = 1.3  # baseline MDD × 1.3
_DEFAULT_MIN_TRADES = 10


def _build_signal_generator(preset: StrategyPreset, overrides: dict[str, float]) -> SignalGenerator:
    """Build a SignalGenerator with candidate parameters applied."""
    merged = _apply_overrides(preset, overrides)
    return SignalGenerator(
        strategy_id=merged.strategy_id,
        scoring_mode=merged.scoring_mode,
        entry_mode=merged.entry_mode,
        score_weights=merged.score_weights,
        tf_weights=merged.tf_weights,
        buy_threshold=merged.buy_threshold,
        sell_threshold=merged.sell_threshold,
        majority_min=merged.majority_min,
        use_daily_gate=merged.use_daily_gate,
        macro_weight=merged.macro_weight,
    )


def run_gate1_validation(
    preset: StrategyPreset,
    candidate_params: dict[str, float],
    ohlcv: dict[str, pd.DataFrame],
    baseline_metrics: dict[str, Any],
    initial_balance: float = 50_000_000,
    primary_tf: str = "1h",
) -> ValidationResult:
    """Run Gate 1 validation: 3-window walk-forward OOS backtest.

    Args:
        preset: Base strategy preset.
        candidate_params: Optimized parameters to validate.
        ohlcv: OHLCV data by timeframe.
        baseline_metrics: Metrics from the baseline (pre-optimization) backtest.
        initial_balance: Initial balance for backtest.
        primary_tf: Primary timeframe for bar iteration.

    Returns:
        ValidationResult with per-window metrics, gate checks, and verdict.
    """
    sig = _build_signal_generator(preset, candidate_params)

    # 3-window walk-forward configuration
    # Use moderate windows: ~90d IS, ~30d OOS, step 60d for 3 windows
    primary_df = ohlcv.get(primary_tf)
    if primary_df is None:
        raise ValueError(f"No data for timeframe {primary_tf}")

    total_bars = len(primary_df)
    # Calculate window sizes to get ~3 windows from available data
    # Target: IS=60%, OOS=20% of total, step = OOS size
    oos_bars = max(total_bars // 5, 100)
    is_bars = max(total_bars // 3, oos_bars * 2)
    step_size = oos_bars

    # Ensure we don't exceed available data
    min_needed = is_bars + oos_bars
    if total_bars < min_needed:
        is_bars = total_bars * 2 // 3
        oos_bars = total_bars // 3
        step_size = oos_bars

    wf_config = WalkForwardConfig(
        is_bars=is_bars,
        oos_bars=oos_bars,
        step_size=step_size,
        min_trades_per_window=2,
    )

    bt_config = BacktestConfig(
        initial_balance_krw=initial_balance,
        fee_rate=0.0005,
        slippage_bps=5.0,
    )

    engine = WalkForwardEngine(
        signal_generator=sig,
        risk_config=preset.risk_config,
        backtest_config=bt_config,
        wf_config=wf_config,
    )

    wf_result = engine.run(ohlcv, primary_tf=primary_tf)

    # Extract per-window metrics
    windows_data = []
    window_returns = []
    window_pfs = []
    window_mdds = []
    total_trades = 0

    for w in wf_result.valid_windows:
        m = w.oos_result.metrics
        ret = m.get("total_return_pct", 0.0)
        pf = m.get("profit_factor", 0.0)
        mdd = m.get("max_drawdown_pct", 0.0)
        trades = m.get("total_trades", 0)

        window_returns.append(ret)
        window_pfs.append(pf if pf and pf != float("inf") else 0.0)
        window_mdds.append(mdd)
        total_trades += trades

        windows_data.append({
            "window_id": w.window_id,
            "is_range": [w.is_start_idx, w.is_end_idx],
            "oos_range": [w.oos_start_idx, w.oos_end_idx],
            "return_pct": round(ret, 2),
            "pf": round(pf, 2) if pf and pf != float("inf") else 0.0,
            "mdd": round(mdd, 2),
            "trades": trades,
        })

    # Calculate averages
    n_windows = len(window_returns) or 1
    avg_return = sum(window_returns) / n_windows
    avg_pf = sum(window_pfs) / n_windows
    avg_mdd = sum(window_mdds) / n_windows if window_mdds else 0.0

    # Gate checks against baseline
    baseline_return = baseline_metrics.get("total_return_pct", 0.0) or 0.0
    baseline_mdd = baseline_metrics.get("max_drawdown_pct", 0.0) or 0.0

    gates: dict[str, GateCheck] = {}

    # Gate 1a: OOS return > baseline + 2%
    return_threshold = baseline_return + _DEFAULT_OOS_RETURN_MARGIN
    gates["oos_return"] = GateCheck(
        name="OOS Return",
        value=avg_return,
        threshold=return_threshold,
        passed=avg_return >= return_threshold,
    )

    # Gate 1b: Profit factor > 1.2
    gates["profit_factor"] = GateCheck(
        name="Profit Factor",
        value=avg_pf,
        threshold=_DEFAULT_PF_MIN,
        passed=avg_pf >= _DEFAULT_PF_MIN,
    )

    # Gate 1c: MDD < baseline MDD × 1.3 (both are negative, so compare absolute)
    mdd_threshold = abs(baseline_mdd) * _DEFAULT_MDD_FACTOR if baseline_mdd else 15.0
    gates["mdd"] = GateCheck(
        name="Max Drawdown",
        value=abs(avg_mdd),
        threshold=mdd_threshold,
        passed=abs(avg_mdd) <= mdd_threshold,
    )

    # Gate 1d: Total trades >= 10
    gates["trade_count"] = GateCheck(
        name="Trade Count",
        value=float(total_trades),
        threshold=float(_DEFAULT_MIN_TRADES),
        passed=total_trades >= _DEFAULT_MIN_TRADES,
    )

    # Verdict
    all_passed = all(g.passed for g in gates.values())
    critical_failed = not gates["oos_return"].passed or not gates["mdd"].passed
    if all_passed:
        verdict = "pass"
    elif critical_failed:
        verdict = "fail"
    else:
        verdict = "warn"

    logger.info(
        "Gate 1 validation: verdict=%s (return=%.2f, pf=%.2f, mdd=%.2f, trades=%d)",
        verdict, avg_return, avg_pf, avg_mdd, total_trades,
    )

    return ValidationResult(
        windows=windows_data,
        avg_return_pct=avg_return,
        avg_pf=avg_pf,
        avg_mdd=avg_mdd,
        total_trades=total_trades,
        gates=gates,
        verdict=verdict,
    )
