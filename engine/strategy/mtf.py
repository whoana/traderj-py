"""Multi-timeframe aggregation.

Aggregates TimeframeScore objects across timeframes using:
  - WEIGHTED: TF-weighted sum
  - MAJORITY: Count of agreeing TFs (min required)
  - Daily Gate: 1d EMA alignment for buy-side filtering
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from shared.enums import EntryMode
from engine.strategy.scoring import ScoreWeights, TimeframeScore


@dataclass(frozen=True)
class DailyGateResult:
    """Daily Gate check result."""

    passed: bool
    ema_short: float
    ema_medium: float
    reason: str


def check_daily_gate(daily_df: pd.DataFrame | None) -> DailyGateResult:
    """Check 1d EMA alignment for buy permission.

    Rules:
      - EMA20(1d) > EMA50(1d) -> buy allowed
      - EMA20(1d) <= EMA50(1d) -> buy blocked
      - Sell signals always pass (position protection)
      - None daily_df -> gate disabled (passed=True)
    """
    if daily_df is None or daily_df.empty:
        return DailyGateResult(
            passed=True, ema_short=0, ema_medium=0, reason="gate_disabled"
        )

    last = daily_df.iloc[-1]
    ema_s = last.get("ema_short", 0)
    ema_m = last.get("ema_medium", 0)

    if pd.notna(ema_s) and pd.notna(ema_m) and ema_s > ema_m:
        return DailyGateResult(
            passed=True, ema_short=float(ema_s), ema_medium=float(ema_m),
            reason="bullish_alignment",
        )
    return DailyGateResult(
        passed=False, ema_short=float(ema_s) if pd.notna(ema_s) else 0,
        ema_medium=float(ema_m) if pd.notna(ema_m) else 0,
        reason="bearish_alignment",
    )


def aggregate_mtf(
    scores: dict[str, TimeframeScore],
    weights: ScoreWeights,
    tf_weights: dict[str, float],
    entry_mode: EntryMode = EntryMode.WEIGHTED,
    buy_threshold: float = 0.15,
    majority_min: int = 2,
) -> float:
    """Aggregate multi-timeframe scores into a single value.

    Args:
        scores: TF -> TimeframeScore mapping.
        weights: Sub-score weights (ScoreWeights).
        tf_weights: TF weights (must sum to ~1.0).
        entry_mode: Aggregation mode.
        buy_threshold: Threshold for counting bullish TFs in MAJORITY mode.
        majority_min: Minimum bullish TFs required in MAJORITY mode.

    Returns:
        Aggregated score in [-1, +1].
    """
    if not scores:
        return 0.0

    if entry_mode == EntryMode.WEIGHTED:
        return _aggregate_weighted(scores, weights, tf_weights)
    elif entry_mode == EntryMode.MAJORITY:
        return _aggregate_majority(
            scores, weights, tf_weights, buy_threshold, majority_min
        )
    else:
        return _aggregate_weighted(scores, weights, tf_weights)


def _aggregate_weighted(
    scores: dict[str, TimeframeScore],
    weights: ScoreWeights,
    tf_weights: dict[str, float],
) -> float:
    """TF-weighted sum of combined scores."""
    total = 0.0
    weight_sum = 0.0
    for tf, score in scores.items():
        tw = tf_weights.get(tf, 0.0)
        total += score.combined(weights) * tw
        weight_sum += tw

    if weight_sum == 0:
        return 0.0
    return max(-1.0, min(1.0, total / weight_sum))


def _aggregate_majority(
    scores: dict[str, TimeframeScore],
    weights: ScoreWeights,
    tf_weights: dict[str, float],
    buy_threshold: float,
    majority_min: int,
) -> float:
    """Count TFs agreeing on direction. Require majority_min for signal."""
    bullish_count = 0
    bearish_count = 0
    for tf, score in scores.items():
        combined = score.combined(weights)
        if combined >= buy_threshold:
            bullish_count += 1
        elif combined <= -buy_threshold:
            bearish_count += 1

    # Use weighted score as magnitude but require majority agreement
    weighted = _aggregate_weighted(scores, weights, tf_weights)

    if bullish_count >= majority_min and weighted > 0:
        return weighted
    elif bearish_count >= majority_min and weighted < 0:
        return weighted
    return 0.0
