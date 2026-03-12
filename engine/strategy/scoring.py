"""TimeframeScore and ScoreWeights for differential weighted scoring.

Two scoring modes:
  - TREND_FOLLOW: trend(0.50), momentum(0.30), volume(0.20)
  - HYBRID: reversal(0.40), quick_momentum(0.40), breakout(0.20)
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.enums import ScoringMode


@dataclass(frozen=True)
class ScoreWeights:
    """Sub-score weights. Must sum to 1.0."""

    w1: float  # TREND_FOLLOW: trend,   HYBRID: reversal
    w2: float  # TREND_FOLLOW: momentum, HYBRID: quick_momentum
    w3: float  # TREND_FOLLOW: volume,   HYBRID: breakout

    def __post_init__(self) -> None:
        total = self.w1 + self.w2 + self.w3
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Score weights must sum to 1.0, got {total}")


TREND_FOLLOW_WEIGHTS = ScoreWeights(0.50, 0.30, 0.20)
HYBRID_WEIGHTS = ScoreWeights(0.40, 0.40, 0.20)


def default_weights(mode: ScoringMode) -> ScoreWeights:
    """Return default weights for the given scoring mode."""
    if mode == ScoringMode.TREND_FOLLOW:
        return TREND_FOLLOW_WEIGHTS
    return HYBRID_WEIGHTS


@dataclass
class TimeframeScore:
    """Three sub-scores for a single timeframe."""

    timeframe: str
    s1: float  # trend or reversal
    s2: float  # momentum or quick_momentum
    s3: float  # volume or breakout

    def combined(self, weights: ScoreWeights) -> float:
        """Differentially weighted combination. Returns [-1, +1]."""
        raw = self.s1 * weights.w1 + self.s2 * weights.w2 + self.s3 * weights.w3
        return max(-1.0, min(1.0, raw))

    def as_dict(self, weights: ScoreWeights) -> dict:
        """Serialize for Signal.details."""
        return {
            "s1": round(self.s1, 4),
            "s2": round(self.s2, 4),
            "s3": round(self.s3, 4),
            "combined": round(self.combined(weights), 4),
            "weights": [weights.w1, weights.w2, weights.w3],
        }
