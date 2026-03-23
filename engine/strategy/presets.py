"""Strategy presets — predefined configurations for SignalGenerator.

9 presets: default + STR-001 through STR-008.
Each defines scoring mode, entry mode, TF weights, and thresholds.
STR-007/008 are bear market defensive presets with strict entry conditions.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.strategy.scoring import HYBRID_WEIGHTS, TREND_FOLLOW_WEIGHTS, ScoreWeights
from shared.enums import EntryMode, ScoringMode


@dataclass(frozen=True)
class StrategyPreset:
    """Complete strategy configuration preset."""

    name: str
    strategy_id: str
    scoring_mode: ScoringMode
    entry_mode: EntryMode
    score_weights: ScoreWeights
    tf_weights: dict[str, float]
    buy_threshold: float
    sell_threshold: float
    majority_min: int
    use_daily_gate: bool
    macro_weight: float


# Tuned 2026-03-07 via grid search (90d walk-forward: 60d train / 30d OOS)
# Key changes: thresholds lowered, macro_weight reduced for backtest,
# some strategies switched to HYBRID based on OOS results.

DEFAULT_PRESET = StrategyPreset(
    name="Default Trend Follow",
    strategy_id="default",
    scoring_mode=ScoringMode.TREND_FOLLOW,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=TREND_FOLLOW_WEIGHTS,
    tf_weights={"1h": 0.3, "4h": 0.5},
    buy_threshold=0.08,
    sell_threshold=-0.08,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.0,
)

# STR-001: Conservative Trend Follow (4h primary)
STR_001 = StrategyPreset(
    name="Conservative Trend (4h)",
    strategy_id="STR-001",
    scoring_mode=ScoringMode.TREND_FOLLOW,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=TREND_FOLLOW_WEIGHTS,
    tf_weights={"1h": 0.2, "4h": 0.5, "1d": 0.3},
    buy_threshold=0.10,
    sell_threshold=-0.10,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.10,
)

# STR-002: Aggressive Trend Follow (1h primary)
STR_002 = StrategyPreset(
    name="Aggressive Trend (1h)",
    strategy_id="STR-002",
    scoring_mode=ScoringMode.TREND_FOLLOW,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=TREND_FOLLOW_WEIGHTS,
    tf_weights={"1h": 0.5, "4h": 0.5},
    buy_threshold=0.05,
    sell_threshold=-0.05,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.0,
)

# STR-003: Hybrid Reversal (4h+1d — top performer in grid search)
STR_003 = StrategyPreset(
    name="Hybrid Reversal (4h/1d)",
    strategy_id="STR-003",
    scoring_mode=ScoringMode.HYBRID,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=HYBRID_WEIGHTS,
    tf_weights={"4h": 0.4, "1d": 0.6},
    buy_threshold=0.10,
    sell_threshold=-0.10,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.10,
)

# STR-004: Majority Vote Trend
STR_004 = StrategyPreset(
    name="Majority Vote Trend",
    strategy_id="STR-004",
    scoring_mode=ScoringMode.TREND_FOLLOW,
    entry_mode=EntryMode.MAJORITY,
    score_weights=TREND_FOLLOW_WEIGHTS,
    tf_weights={"1h": 0.3, "4h": 0.5},
    buy_threshold=0.08,
    sell_threshold=-0.08,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.0,
)

# STR-005: Low-frequency Hybrid (4h+1d)
STR_005 = StrategyPreset(
    name="Low-Frequency Hybrid",
    strategy_id="STR-005",
    scoring_mode=ScoringMode.HYBRID,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=HYBRID_WEIGHTS,
    tf_weights={"4h": 0.4, "1d": 0.6},
    buy_threshold=0.12,
    sell_threshold=-0.12,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.0,
)

# STR-006: Scalper (1h/4h)
STR_006 = StrategyPreset(
    name="Scalper (1h/4h)",
    strategy_id="STR-006",
    scoring_mode=ScoringMode.TREND_FOLLOW,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=ScoreWeights(0.40, 0.35, 0.25),
    tf_weights={"1h": 0.5, "4h": 0.5},
    buy_threshold=0.05,
    sell_threshold=-0.05,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.0,
)


# STR-007: Bear Defensive (bear market, high volatility)
# Very strict entry: only buy on extreme oversold reversals.
# Fast exit to minimize drawdown.
# daily_gate=False: EMA gate blocks ALL buys in bear market (self-contradictory).
STR_007 = StrategyPreset(
    name="Bear Defensive (1d)",
    strategy_id="STR-007",
    scoring_mode=ScoringMode.HYBRID,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=HYBRID_WEIGHTS,
    tf_weights={"4h": 0.3, "1d": 0.7},
    buy_threshold=0.18,
    sell_threshold=-0.03,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.20,
)

# STR-008: Bear Cautious Reversal (bear market, low volatility)
# Slightly less strict than STR-007. No daily gate (would permanently block).
STR_008 = StrategyPreset(
    name="Bear Cautious Reversal (4h/1d)",
    strategy_id="STR-008",
    scoring_mode=ScoringMode.HYBRID,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=HYBRID_WEIGHTS,
    tf_weights={"4h": 0.4, "1d": 0.6},
    buy_threshold=0.15,
    sell_threshold=-0.08,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.15,
)


STRATEGY_PRESETS: dict[str, StrategyPreset] = {
    "default": DEFAULT_PRESET,
    "STR-001": STR_001,
    "STR-002": STR_002,
    "STR-003": STR_003,
    "STR-004": STR_004,
    "STR-005": STR_005,
    "STR-006": STR_006,
    "STR-007": STR_007,
    "STR-008": STR_008,
}
