"""Rule-based fallback logic when all LLM providers are unavailable."""

from __future__ import annotations

import logging

from engine.tuner.enums import DiagnosisDirection
from engine.tuner.models import EvalMetrics, OptimizerCandidate, ParamRecommendation

logger = logging.getLogger(__name__)


class DegradedFallback:
    """Rule-based diagnosis, selection, and approval when LLMs are down."""

    def diagnose(
        self,
        metrics: EvalMetrics,
        current_params: dict[str, float],
    ) -> list[ParamRecommendation]:
        """Rule-based diagnosis. Always confidence=LOW equivalent."""
        recommendations: list[ParamRecommendation] = []

        if metrics.win_rate < 0.30:
            recommendations.append(
                ParamRecommendation(
                    name="buy_threshold",
                    direction=DiagnosisDirection.INCREASE,
                    reason=f"win_rate {metrics.win_rate:.1%} < 30%: entry criteria too loose",
                )
            )

        if metrics.win_rate > 0.70 and metrics.profit_factor < 1.5:
            recommendations.append(
                ParamRecommendation(
                    name="reward_risk_ratio",
                    direction=DiagnosisDirection.INCREASE,
                    reason=f"win_rate {metrics.win_rate:.1%} high but PF {metrics.profit_factor:.2f} low: widen TP",
                )
            )

        if metrics.avg_holding_hours < 3.0:
            recommendations.append(
                ParamRecommendation(
                    name="sell_threshold",
                    direction=DiagnosisDirection.DECREASE,
                    reason=f"avg hold {metrics.avg_holding_hours:.1f}h < 3h: premature exit",
                )
            )

        if metrics.signal_accuracy < 0.20:
            recommendations.append(
                ParamRecommendation(
                    name="buy_threshold",
                    direction=DiagnosisDirection.INCREASE,
                    reason=f"signal accuracy {metrics.signal_accuracy:.1%} < 20%: too many false signals",
                )
            )

        if metrics.max_drawdown > 0.05:
            recommendations.append(
                ParamRecommendation(
                    name="max_position_pct",
                    direction=DiagnosisDirection.DECREASE,
                    reason=f"MDD {metrics.max_drawdown:.2%} > 5%: reduce position size",
                )
            )

        if metrics.avg_r_multiple < 0.5:
            recommendations.append(
                ParamRecommendation(
                    name="atr_stop_multiplier",
                    direction=DiagnosisDirection.INCREASE,
                    reason=f"avg R-multiple {metrics.avg_r_multiple:.2f} < 0.5: SL too tight",
                )
            )

        if not recommendations:
            logger.info("Degraded diagnosis: no issues detected for %s", metrics.strategy_id)

        return recommendations

    def select_candidate(self, candidates: list[OptimizerCandidate]) -> OptimizerCandidate:
        """Select candidate with highest validation PF."""
        return max(candidates, key=lambda c: c.validation_pf)

    def approve(
        self,
        candidate: OptimizerCandidate,
        baseline_pf: float,
        baseline_mdd: float,
    ) -> bool:
        """Approve if validation PF >= 1.0 and MDD not worse than baseline * 1.5."""
        return candidate.validation_pf >= 1.0 and candidate.validation_mdd <= baseline_mdd * 1.5
