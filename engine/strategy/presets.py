"""Strategy presets — predefined configurations for SignalGenerator.

9 presets: default + STR-001 through STR-008.
Each defines scoring mode, entry mode, TF weights, and thresholds.
STR-007/008 are bear market defensive presets with strict entry conditions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from engine.strategy.risk import RiskConfig
from engine.strategy.scoring import HYBRID_WEIGHTS, TREND_FOLLOW_WEIGHTS, ScoreWeights
from shared.enums import EntryMode, ScoringMode

logger = logging.getLogger(__name__)


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
    risk_config: RiskConfig | None = None  # per-preset risk overrides


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


# STR-009: Bull Trend Rider (strong uptrend — wide stops, ride the wave)
# Designed for +20%+ monthly moves. Low entry bar, very wide trailing.
STR_009 = StrategyPreset(
    name="Bull Trend Rider (4h)",
    strategy_id="STR-009",
    scoring_mode=ScoringMode.TREND_FOLLOW,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=TREND_FOLLOW_WEIGHTS,
    tf_weights={"1h": 0.2, "4h": 0.5, "1d": 0.3},
    buy_threshold=0.04,
    sell_threshold=-0.15,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.0,
    risk_config=RiskConfig(
        max_position_pct=0.35,
        min_position_pct=0.10,
        target_risk_pct=0.03,
        stop_loss_pct=0.06,
        atr_stop_multiplier=3.0,
        trailing_stop_activation_pct=0.05,
        trailing_stop_distance_pct=0.04,
        reward_risk_ratio=3.0,
    ),
)

# STR-010: Swing Trend Follow (moderate trend — balanced risk/reward)
# Middle ground between scalping and trend riding.
STR_010 = StrategyPreset(
    name="Swing Trend (4h/1d)",
    strategy_id="STR-010",
    scoring_mode=ScoringMode.TREND_FOLLOW,
    entry_mode=EntryMode.WEIGHTED,
    score_weights=TREND_FOLLOW_WEIGHTS,
    tf_weights={"4h": 0.4, "1d": 0.6},
    buy_threshold=0.06,
    sell_threshold=-0.12,
    majority_min=2,
    use_daily_gate=False,
    macro_weight=0.05,
    risk_config=RiskConfig(
        max_position_pct=0.25,
        min_position_pct=0.08,
        target_risk_pct=0.025,
        stop_loss_pct=0.05,
        atr_stop_multiplier=2.5,
        trailing_stop_activation_pct=0.03,
        trailing_stop_distance_pct=0.03,
        reward_risk_ratio=2.5,
    ),
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
    "STR-009": STR_009,
    "STR-010": STR_010,
}

# --- Flat JSON key → StrategyPreset field mapping ---
# Tier-1 tunable parameters use flat keys in preset_overrides.json.
# This maps them to the nested dataclass structure.
_DIRECT_FIELDS = {"buy_threshold", "sell_threshold", "macro_weight"}
_TF_WEIGHT_KEYS = {"tf_weight_1h": "1h", "tf_weight_4h": "4h", "tf_weight_1d": "1d"}
_SCORE_WEIGHT_KEYS = {"score_w1": "w1", "score_w2": "w2", "score_w3": "w3"}


def _apply_overrides(preset: StrategyPreset, overrides: dict[str, float]) -> StrategyPreset:
    """Apply flat override params to a frozen StrategyPreset, returning a new instance."""
    if not overrides:
        return preset

    kwargs: dict[str, object] = {}

    # Direct scalar fields
    for key in _DIRECT_FIELDS:
        if key in overrides:
            kwargs[key] = overrides[key]

    # tf_weights: merge into existing dict and normalize
    tf_updates = {tf: overrides[k] for k, tf in _TF_WEIGHT_KEYS.items() if k in overrides}
    if tf_updates:
        merged_tf = {**preset.tf_weights, **tf_updates}
        tf_total = sum(merged_tf.values())
        if tf_total > 0:
            merged_tf = {k: v / tf_total for k, v in merged_tf.items()}
        kwargs["tf_weights"] = merged_tf

    # score_weights: rebuild ScoreWeights (normalize to sum=1.0)
    sw_updates = {attr: overrides[k] for k, attr in _SCORE_WEIGHT_KEYS.items() if k in overrides}
    if sw_updates:
        w1 = sw_updates.get("w1", preset.score_weights.w1)
        w2 = sw_updates.get("w2", preset.score_weights.w2)
        w3 = sw_updates.get("w3", preset.score_weights.w3)
        sw_total = w1 + w2 + w3
        if sw_total > 0 and abs(sw_total - 1.0) > 0.001:
            w1 = w1 / sw_total
            w2 = w2 / sw_total
            w3 = 1.0 - w1 - w2
        kwargs["score_weights"] = ScoreWeights(w1=w1, w2=w2, w3=w3)

    if not kwargs:
        return preset
    return replace(preset, **kwargs)


def load_preset(strategy_id: str, data_dir: str | None = None) -> StrategyPreset:
    """Load a strategy preset with JSON overrides applied.

    1. Look up base preset from STRATEGY_PRESETS (falls back to default).
    2. Load sparse overrides from /data/preset_overrides.json.
    3. Return merged preset (new frozen instance).
    """
    from engine.strategy.preset_override import get_preset_overrides

    base = STRATEGY_PRESETS.get(strategy_id)
    if base is None:
        logger.warning("Unknown strategy_id %r, using default preset", strategy_id)
        base = DEFAULT_PRESET

    overrides = get_preset_overrides(strategy_id, data_dir)
    if overrides:
        logger.info("Applying %d override(s) for %s: %s", len(overrides), strategy_id, overrides)
        return _apply_overrides(base, overrides)
    return base
