"""SignalGenerator — strategy signal pipeline orchestrator.

8-step pipeline:
  1. Compute indicators per timeframe
  2. Apply Z-score normalization
  3. Run scoring functions -> TimeframeScore
  4. Classify market regime (optional)
  5. Check daily gate (optional)
  6. MTF aggregation -> technical_score
  7. Integrate macro score
  8. Determine final direction (BUY/SELL/HOLD)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from engine.strategy.filters import (
    breakout_score,
    momentum_score,
    quick_momentum_score,
    reversal_score,
    trend_score,
    volume_score,
)
from engine.strategy.indicators import IndicatorConfig, compute_indicators
from engine.strategy.mtf import DailyGateResult, aggregate_mtf, check_daily_gate
from engine.strategy.normalizer import normalize_indicators
from engine.strategy.scoring import (
    ScoreWeights,
    TimeframeScore,
    default_weights,
)
from shared.enums import EntryMode, ScoringMode, SignalDirection

logger = logging.getLogger(__name__)

_TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


@dataclass
class SignalResult:
    """Signal generation result."""

    timestamp: datetime
    symbol: str
    direction: SignalDirection
    score: float
    details: dict[str, Any]


class SignalGenerator:
    """Strategy signal generation pipeline orchestrator."""

    def __init__(
        self,
        strategy_id: str,
        scoring_mode: ScoringMode = ScoringMode.TREND_FOLLOW,
        entry_mode: EntryMode = EntryMode.WEIGHTED,
        score_weights: ScoreWeights | None = None,
        tf_weights: dict[str, float] | None = None,
        buy_threshold: float = 0.15,
        sell_threshold: float = -0.15,
        majority_min: int = 2,
        use_daily_gate: bool = False,
        macro_weight: float = 0.2,
        indicator_config: IndicatorConfig | None = None,
    ) -> None:
        self.strategy_id = strategy_id
        self.scoring_mode = scoring_mode
        self.entry_mode = entry_mode
        self.score_weights = score_weights or default_weights(scoring_mode)
        self.tf_weights = tf_weights or {"1h": 0.3, "4h": 0.5}
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.majority_min = majority_min
        self.use_daily_gate = use_daily_gate
        self.macro_weight = macro_weight
        self.indicator_config = indicator_config or IndicatorConfig()

    def apply_preset(self, preset) -> None:
        """Hot-swap strategy parameters from a StrategyPreset."""
        self.scoring_mode = preset.scoring_mode
        self.entry_mode = preset.entry_mode
        self.score_weights = preset.score_weights
        self.tf_weights = preset.tf_weights
        self.buy_threshold = preset.buy_threshold
        self.sell_threshold = preset.sell_threshold
        self.majority_min = preset.majority_min
        self.use_daily_gate = preset.use_daily_gate
        self.macro_weight = preset.macro_weight
        logger.info(
            "SignalGenerator preset applied: %s (mode=%s, tf=%s)",
            preset.strategy_id, preset.scoring_mode.value, preset.tf_weights,
        )

    def generate(
        self,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        macro_score: float = 0.0,
        symbol: str = "BTC/KRW",
    ) -> SignalResult:
        """Generate a trading signal.

        Args:
            ohlcv_by_tf: {"1h": df, "4h": df, "1d": df (gate only)}
            macro_score: Pre-computed macro score in [-1, +1].
            symbol: Trading pair.

        Returns:
            SignalResult with direction, score, and details.
        """
        now = datetime.now(UTC)

        # Step 1-3: Compute indicators + scoring per TF
        tf_scores: dict[str, TimeframeScore] = {}
        tf_details: dict[str, dict] = {}

        for tf, df in ohlcv_by_tf.items():
            if tf == "1d" and self.use_daily_gate:
                continue
            if df.empty or tf not in self.tf_weights:
                continue

            # Skip indicator computation if already precomputed (backtest optimization)
            if "z_macd_hist" in df.columns:
                df_norm = df
            elif "ema_short" in df.columns:
                df_norm = normalize_indicators(df)
            else:
                df_ind = compute_indicators(df, self.indicator_config)
                df_norm = normalize_indicators(df_ind)

            if self.scoring_mode == ScoringMode.HYBRID:
                s1 = reversal_score(df_norm)
                s2 = quick_momentum_score(df_norm)
                s3 = breakout_score(df_norm)
            else:
                s1 = trend_score(df_norm)
                s2 = momentum_score(df_norm)
                s3 = volume_score(df_norm)

            ts = TimeframeScore(timeframe=tf, s1=s1, s2=s2, s3=s3)
            tf_scores[tf] = ts
            tf_details[tf] = ts.as_dict(self.score_weights)

        # Step 4: Daily Gate
        daily_gate: DailyGateResult | None = None
        if self.use_daily_gate and "1d" in ohlcv_by_tf:
            df_1d_raw = ohlcv_by_tf["1d"]
            if "ema_short" in df_1d_raw.columns:
                daily_gate = check_daily_gate(df_1d_raw)
            elif len(df_1d_raw) >= 50:
                df_1d = compute_indicators(df_1d_raw, self.indicator_config)
                daily_gate = check_daily_gate(df_1d)
            else:
                daily_gate = check_daily_gate(None)

        # Step 5: MTF aggregation
        technical_score = aggregate_mtf(
            scores=tf_scores,
            weights=self.score_weights,
            tf_weights=self.tf_weights,
            entry_mode=self.entry_mode,
            buy_threshold=self.buy_threshold,
            majority_min=self.majority_min,
        )

        # Step 6-7: Combine with macro
        combined = (
            technical_score * (1 - self.macro_weight)
            + macro_score * self.macro_weight
        )

        # Step 8: Direction decision
        effective_buy_th = self.buy_threshold
        effective_sell_th = self.sell_threshold

        if daily_gate and not daily_gate.passed and combined >= effective_buy_th:
            direction = SignalDirection.HOLD
        elif combined >= effective_buy_th:
            direction = SignalDirection.BUY
        elif combined <= effective_sell_th:
            direction = SignalDirection.SELL
        else:
            direction = SignalDirection.HOLD

        details: dict[str, Any] = {
            "strategy_id": self.strategy_id,
            "scoring_mode": self.scoring_mode.value,
            "entry_mode": self.entry_mode.value,
            "technical": round(technical_score, 4),
            "macro_raw": round(macro_score, 4),
            "score_weights": [
                self.score_weights.w1,
                self.score_weights.w2,
                self.score_weights.w3,
            ],
            "effective_thresholds": {
                "buy": round(effective_buy_th, 4),
                "sell": round(effective_sell_th, 4),
            },
            "daily_gate_status": daily_gate.reason if daily_gate else "disabled",
            "tf_scores": tf_details,
        }

        logger.info(
            "signal_generated: strategy=%s direction=%s score=%.4f tech=%.4f",
            self.strategy_id,
            direction.value,
            combined,
            technical_score,
        )

        return SignalResult(
            timestamp=now,
            symbol=symbol,
            direction=direction,
            score=round(combined, 6),
            details=details,
        )
