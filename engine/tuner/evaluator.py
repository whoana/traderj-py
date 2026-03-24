"""Strategy performance evaluator with LLM diagnosis."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from engine.strategy.backtest.metrics import compute_metrics
from engine.tuner.config import get_bounds_for_tier
from engine.tuner.degraded import DegradedFallback
from engine.tuner.enums import DiagnosisDirection, LLMConfidence, LLMProviderName, TierLevel, TuningStatus
from engine.tuner.models import (
    EvalMetrics,
    EvaluationResult,
    LLMDiagnosis,
    ParamRecommendation,
    TuningReport,
)
from engine.tuner.prompts import DIAGNOSIS_TEMPLATE, SYSTEM_PROMPT, parse_llm_json
from engine.tuner.provider_router import ProviderRouter
from engine.tuner.store import TunerStore

logger = logging.getLogger(__name__)


class StrategyEvaluator:
    """Evaluates strategy performance and produces LLM-assisted diagnosis."""

    def __init__(
        self,
        data_store: object,
        tuner_store: TunerStore,
        provider_router: ProviderRouter,
        degraded: DegradedFallback,
        notifier: object | None = None,
    ) -> None:
        self._data_store = data_store
        self._tuner_store = tuner_store
        self._router = provider_router
        self._degraded = degraded
        self._notifier = notifier

    async def evaluate(
        self,
        strategy_id: str,
        eval_days: int = 7,
        tier: TierLevel = TierLevel.TIER_1,
        current_params: dict[str, float] | None = None,
        now: datetime | None = None,
    ) -> EvaluationResult:
        """Evaluate strategy performance over eval_days and produce diagnosis."""
        now = now or datetime.now(tz=timezone.utc)
        start = now - timedelta(days=eval_days)
        eval_window = f"{start.strftime('%Y-%m-%d')}~{now.strftime('%Y-%m-%d')}"

        # 1. Query orders and positions from DataStore
        orders = await self._data_store.get_orders(strategy_id=strategy_id, limit=500)  # type: ignore[attr-defined]
        positions = await self._data_store.get_positions(strategy_id=strategy_id)  # type: ignore[attr-defined]

        # Filter to eval window
        window_orders = [o for o in orders if o.created_at and o.created_at >= start]
        window_positions = [p for p in positions if p.opened_at and p.opened_at >= start]

        # 2. Compute metrics
        total_trades = len(window_orders) // 2  # buy + sell pairs
        metrics = self._compute_eval_metrics(
            strategy_id=strategy_id,
            eval_window=eval_window,
            orders=window_orders,
            positions=window_positions,
        )

        # 3. Check minimum trades
        min_trades = 3  # from schedule settings
        if metrics.total_trades < min_trades:
            logger.info(
                "Skipping tuning for %s: %d trades < %d minimum",
                strategy_id,
                metrics.total_trades,
                min_trades,
            )
            return EvaluationResult(
                metrics=metrics,
                diagnosis=None,
                rule_diagnosis=[],
                should_tune=False,
                skip_reason="insufficient_trades",
            )

        # 4. Check if metrics are acceptable
        if metrics.profit_factor > 1.5 and metrics.win_rate > 0.40:
            logger.info("Strategy %s metrics acceptable (PF=%.2f, WR=%.1%%)", strategy_id, metrics.profit_factor, metrics.win_rate * 100)
            return EvaluationResult(
                metrics=metrics,
                diagnosis=None,
                rule_diagnosis=[],
                should_tune=False,
                skip_reason="metrics_acceptable",
            )

        # 5. Always compute rule-based diagnosis
        rule_diagnosis = self._degraded.diagnose(metrics, current_params or {})

        # 6. Try LLM diagnosis
        diagnosis: LLMDiagnosis | None = None
        try:
            diagnosis = await self._llm_diagnose(
                strategy_id=strategy_id,
                metrics=metrics,
                tier=tier,
                current_params=current_params or {},
                eval_days=eval_days,
            )
        except Exception:
            logger.exception("LLM diagnosis failed for %s, using rule-based fallback", strategy_id)

        # 7. Save tuning report
        tuning_id = f"tune-{strategy_id}-{now.strftime('%Y%m%d%H%M%S')}"
        report = TuningReport(
            tuning_id=tuning_id,
            created_at=now,
            eval_window=eval_window,
            strategy_id=strategy_id,
            metrics=metrics,
            recommendations=diagnosis.recommended_params if diagnosis else rule_diagnosis,
            applied_changes=[],
            status=TuningStatus.PENDING,
        )
        await self._tuner_store.save_tuning_report(report)

        return EvaluationResult(
            metrics=metrics,
            diagnosis=diagnosis,
            rule_diagnosis=rule_diagnosis,
            should_tune=True,
            skip_reason=None,
        )

    def _compute_eval_metrics(
        self,
        strategy_id: str,
        eval_window: str,
        orders: list,
        positions: list,
    ) -> EvalMetrics:
        """Compute EvalMetrics from orders and positions."""
        closed = [p for p in positions if hasattr(p, "status") and str(p.status) == "closed"]
        total_trades = len(closed)

        if total_trades == 0:
            return EvalMetrics(
                strategy_id=strategy_id,
                eval_window=eval_window,
                regime=None,
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                avg_r_multiple=0.0,
                signal_accuracy=0.0,
                avg_holding_hours=0.0,
                total_return_pct=0.0,
                sharpe_ratio=0.0,
            )

        wins = [p for p in closed if hasattr(p, "realized_pnl") and float(p.realized_pnl) > 0]
        losses = [p for p in closed if hasattr(p, "realized_pnl") and float(p.realized_pnl) <= 0]

        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(float(p.realized_pnl) for p in wins) if wins else 0.0
        gross_loss = abs(sum(float(p.realized_pnl) for p in losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

        total_pnl = gross_profit - gross_loss
        avg_r = total_pnl / total_trades if total_trades > 0 else 0.0

        # Holding hours
        holding_hours: list[float] = []
        for p in closed:
            if hasattr(p, "opened_at") and hasattr(p, "closed_at") and p.opened_at and p.closed_at:
                delta = p.closed_at - p.opened_at
                holding_hours.append(delta.total_seconds() / 3600)
        avg_holding = sum(holding_hours) / len(holding_hours) if holding_hours else 0.0

        return EvalMetrics(
            strategy_id=strategy_id,
            eval_window=eval_window,
            regime=None,
            total_trades=total_trades,
            win_rate=win_rate,
            profit_factor=min(profit_factor, 99.0),
            max_drawdown=0.0,
            avg_r_multiple=avg_r,
            signal_accuracy=0.0,
            avg_holding_hours=avg_holding,
            total_return_pct=0.0,
            sharpe_ratio=0.0,
        )

    async def _llm_diagnose(
        self,
        strategy_id: str,
        metrics: EvalMetrics,
        tier: TierLevel,
        current_params: dict[str, float],
        eval_days: int,
    ) -> LLMDiagnosis | None:
        """Call LLM for strategy diagnosis."""
        bounds = get_bounds_for_tier(tier)
        adjustable = ", ".join(b.name for b in bounds)

        prompt = DIAGNOSIS_TEMPLATE.format(
            strategy_id=strategy_id,
            strategy_name=strategy_id,
            eval_days=eval_days,
            regime=metrics.regime or "unknown",
            total_trades=metrics.total_trades,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            max_drawdown=metrics.max_drawdown,
            avg_r_multiple=metrics.avg_r_multiple,
            avg_holding_hours=metrics.avg_holding_hours,
            signal_accuracy=metrics.signal_accuracy,
            total_return_pct=metrics.total_return_pct,
            current_params_json=json.dumps(current_params),
            tier=tier.value,
            adjustable_params=adjustable,
        )

        response = await self._router.complete(SYSTEM_PROMPT, prompt)
        if response is None:
            return None

        data = parse_llm_json(response.text)

        recommended = [
            ParamRecommendation(
                name=p["name"],
                direction=DiagnosisDirection(p["direction"]),
                reason=p.get("reason", ""),
            )
            for p in data.get("recommended_params", [])
        ]

        return LLMDiagnosis(
            root_causes=data.get("root_causes", []),
            recommended_params=recommended,
            confidence=LLMConfidence(data.get("confidence", "low")),
            raw_response=response.text,
            provider=LLMProviderName(response.provider),
            model=response.model,
            tokens_used=response.input_tokens + response.output_tokens,
            cost_usd=response.cost_usd,
        )
