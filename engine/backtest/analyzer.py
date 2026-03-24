"""Backtest result analyzer — extracts actionable insights from results.

Provides:
  - analyze_results(): Summary + action recommendations
  - analyze_regime_mapping(): Regime-strategy mapping improvement suggestions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from engine.strategy.regime import REGIME_PRESET_MAP

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegimeMapSuggestion:
    regime: str
    current_strategy: str
    suggested_strategy: str
    current_return_pct: float
    suggested_return_pct: float
    improvement_pct: float
    sample_weeks: int


@dataclass(frozen=True)
class AnalysisSummary:
    best_strategy_id: str | None
    best_strategy_name: str | None
    best_return_pct: float | None
    worst_strategy_id: str | None
    worst_return_pct: float | None
    market_change_pct: float | None
    beat_market_count: int
    total_strategies: int
    insights: list[str]
    actions: list[str]  # available action types: "switch", "regime_map", "optimize"


def analyze_results(result: dict[str, Any]) -> dict[str, Any]:
    """Analyze backtest result and generate summary + action recommendations."""
    mode = result.get("mode", "")
    market = result.get("market", {})
    strategies = result.get("strategies", [])
    ai_regime = result.get("ai_regime")

    market_pct = market.get("change_pct", 0)
    insights: list[str] = []
    actions: list[str] = []

    # Find best/worst strategies
    ranked = [
        s for s in strategies
        if s.get("metrics") and s["metrics"].get("total_return_pct") is not None
    ]
    ranked.sort(key=lambda s: s["metrics"]["total_return_pct"], reverse=True)

    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None

    # Count strategies that beat BTC
    beat_market = sum(
        1 for s in ranked
        if s["metrics"]["total_return_pct"] > market_pct
    )

    # Insights
    if best:
        ret = best["metrics"]["total_return_pct"]
        insights.append(f"최고 성과: {best['strategy_id']} {best.get('name', '')} ({ret:+.2f}%)")

    if worst and len(ranked) > 1:
        ret = worst["metrics"]["total_return_pct"]
        insights.append(f"최저 성과: {worst['strategy_id']} ({ret:+.2f}%)")

    if market_pct != 0:
        insights.append(f"BTC 시장 변동: {market_pct:+.1f}%")
        if beat_market == 0:
            insights.append("모든 전략이 시장 수익률을 하회했습니다")
        elif beat_market == len(ranked):
            insights.append("모든 전략이 시장 수익률을 상회했습니다")
        else:
            insights.append(f"{beat_market}/{len(ranked)}개 전략이 시장 수익률 상회")

    if ai_regime:
        ai_ret = ai_regime.get("aggregate_metrics", {}).get("total_return_pct", 0)
        insights.append(f"AI Regime 종합 수익률: {ai_ret:+.2f}%")
        if best and ai_ret < best["metrics"]["total_return_pct"]:
            insights.append(f"AI Regime이 최고 전략({best['strategy_id']})보다 부진")

    # Available actions
    if mode in ("compare", "single"):
        actions.append("switch")  # Action A: strategy switch
    if mode in ("single", "compare"):
        actions.append("optimize")  # Action C: parameter optimization
    if mode == "ai_regime":
        actions.append("switch")
        actions.append("regime_map")  # Action B
        actions.append("optimize")

    return {
        "best_strategy_id": best["strategy_id"] if best else None,
        "best_strategy_name": best.get("name") if best else None,
        "best_return_pct": best["metrics"]["total_return_pct"] if best else None,
        "worst_strategy_id": worst["strategy_id"] if worst else None,
        "worst_return_pct": worst["metrics"]["total_return_pct"] if worst else None,
        "market_change_pct": market_pct,
        "beat_market_count": beat_market,
        "total_strategies": len(ranked),
        "insights": insights,
        "actions": actions,
    }


def analyze_regime_mapping(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Analyze AI Regime result and suggest regime-strategy mapping improvements.

    Compares the current REGIME_PRESET_MAP with per-regime best performers
    from the compare strategies in the backtest result.
    """
    ai_regime = result.get("ai_regime")
    strategies = result.get("strategies", [])
    if not ai_regime or not strategies:
        return []

    weekly = ai_regime.get("weekly_decisions", [])
    if not weekly:
        return []

    # Build per-regime performance from weekly decisions
    # regime -> list of (current_return, week_info)
    regime_weeks: dict[str, list[dict]] = {}
    for w in weekly:
        regime = w.get("regime", "unknown")
        if regime == "unknown":
            continue
        regime_weeks.setdefault(regime, []).append(w)

    # For each regime, find best performing strategy from compare results
    suggestions: list[dict[str, Any]] = []

    for regime_str, weeks in regime_weeks.items():
        # Current mapping
        regime_enum = None
        for rt in REGIME_PRESET_MAP:
            if rt.value == regime_str:
                regime_enum = rt
                break
        if regime_enum is None:
            continue

        current_sid = REGIME_PRESET_MAP[regime_enum]
        current_total_return = sum(w.get("return_pct", 0) for w in weeks)
        avg_current = current_total_return / len(weeks) if weeks else 0

        # Find best strategy for this regime type from compare results
        # We use overall metrics as a proxy since we don't have per-regime breakdown
        best_sid = current_sid
        best_return = avg_current

        for s in strategies:
            if not s.get("metrics"):
                continue
            sid = s["strategy_id"]
            ret = s["metrics"].get("total_return_pct", -999)
            if ret > best_return:
                best_return = ret / len(weeks) if weeks else ret  # normalize per-week
                best_sid = sid

        if best_sid != current_sid:
            improvement = best_return - avg_current
            suggestions.append({
                "regime": regime_str,
                "current_strategy": current_sid,
                "suggested_strategy": best_sid,
                "current_return_pct": round(avg_current, 2),
                "suggested_return_pct": round(best_return, 2),
                "improvement_pct": round(improvement, 2),
                "sample_weeks": len(weeks),
            })

    # Sort by improvement (biggest first)
    suggestions.sort(key=lambda s: s["improvement_pct"], reverse=True)
    return suggestions
