"""TunerPipeline — full tuning lifecycle orchestrator.

Coordinates: evaluate → optimize → apply → monitor for each strategy.
Manages state transitions and scheduling integration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from engine.tuner.applier import ParameterApplier
from engine.tuner.config import TunerSettings
from engine.tuner.enums import TierLevel, TunerState, TuningStatus
from engine.tuner.evaluator import StrategyEvaluator
from engine.tuner.models import TuningSessionResult
from engine.tuner.optimizer import HybridOptimizer
from engine.tuner.rollback import RollbackMonitor
from engine.tuner.store import TunerStore

logger = logging.getLogger(__name__)


class TunerPipeline:
    """Full tuning pipeline orchestrator."""

    def __init__(
        self,
        evaluator: StrategyEvaluator,
        optimizer: HybridOptimizer,
        applier: ParameterApplier,
        rollback_monitor: RollbackMonitor,
        tuner_store: TunerStore,
        notifier: object | None,
        config: TunerSettings,
    ) -> None:
        self._evaluator = evaluator
        self._optimizer = optimizer
        self._applier = applier
        self._rollback = rollback_monitor
        self._store = tuner_store
        self._notifier = notifier
        self._config = config
        self._state: TunerState = TunerState.IDLE

        # Strategy component references (set via register_strategy)
        self._strategies: dict[str, dict] = {}

    @property
    def state(self) -> TunerState:
        return self._state

    def register_strategy(
        self,
        strategy_id: str,
        signal_generator: object,
        risk_engine: object | None = None,
        regime_switch_manager: object | None = None,
        exchange_client: object | None = None,
    ) -> None:
        """Register live strategy components for parameter application."""
        self._strategies[strategy_id] = {
            "signal_generator": signal_generator,
            "risk_engine": risk_engine,
            "regime_switch_manager": regime_switch_manager,
            "exchange_client": exchange_client,
        }

    async def run_tuning_session(
        self,
        strategy_id: str,
        tier: TierLevel = TierLevel.TIER_1,
        ohlcv_by_tf: dict[str, pd.DataFrame] | None = None,
    ) -> TuningSessionResult:
        """Run a single tuning session for a strategy.

        1. State check: SUSPENDED → skip
        2. Evaluate strategy performance
        3. Optimize if needed
        4. Apply changes
        5. Enter monitoring
        """
        if self._state == TunerState.SUSPENDED:
            logger.warning("Tuner is suspended, skipping %s", strategy_id)
            return TuningSessionResult(
                tuning_id="",
                strategy_id=strategy_id,
                tier=tier,
                status=TuningStatus.REJECTED,
                changes=[],
                eval_metrics=None,
                reason="tuner_suspended",
            )

        components = self._strategies.get(strategy_id, {})
        signal_gen = components.get("signal_generator")
        risk_engine = components.get("risk_engine")
        regime_mgr = components.get("regime_switch_manager")

        if not signal_gen:
            logger.error("Strategy %s not registered with tuner", strategy_id)
            return TuningSessionResult(
                tuning_id="",
                strategy_id=strategy_id,
                tier=tier,
                status=TuningStatus.REJECTED,
                changes=[],
                eval_metrics=None,
                reason="strategy_not_registered",
            )

        # Get current params from signal generator
        current_params = self._extract_current_params(signal_gen, risk_engine, tier)

        # ── Step 1: Evaluate ──
        self._state = TunerState.EVALUATING
        eval_days = self._get_eval_days(tier)

        try:
            evaluation = await self._evaluator.evaluate(
                strategy_id=strategy_id,
                eval_days=eval_days,
                tier=tier,
                current_params=current_params,
            )
        except Exception:
            logger.exception("Evaluation failed for %s", strategy_id)
            self._state = TunerState.IDLE
            return TuningSessionResult(
                tuning_id="",
                strategy_id=strategy_id,
                tier=tier,
                status=TuningStatus.REJECTED,
                changes=[],
                eval_metrics=None,
                reason="evaluation_error",
            )

        if not evaluation.should_tune:
            self._state = TunerState.IDLE
            return TuningSessionResult(
                tuning_id="",
                strategy_id=strategy_id,
                tier=tier,
                status=TuningStatus.REJECTED,
                changes=[],
                eval_metrics=evaluation.metrics,
                reason=evaluation.skip_reason or "no_tuning_needed",
            )

        # ── Step 2: Optimize ──
        self._state = TunerState.OPTIMIZING

        if ohlcv_by_tf is None:
            ohlcv_by_tf = await self._fetch_ohlcv(strategy_id, components)

        try:
            optimization = await self._optimizer.optimize(
                strategy_id=strategy_id,
                evaluation=evaluation,
                tier=tier,
                current_params=current_params,
                ohlcv_by_tf=ohlcv_by_tf,
                signal_generator=signal_gen,
                risk_config=getattr(risk_engine, "config", None) if risk_engine else None,
            )
        except Exception:
            logger.exception("Optimization failed for %s", strategy_id)
            self._state = TunerState.IDLE
            return TuningSessionResult(
                tuning_id="",
                strategy_id=strategy_id,
                tier=tier,
                status=TuningStatus.REJECTED,
                changes=[],
                eval_metrics=evaluation.metrics,
                reason="optimization_error",
            )

        if not optimization.decision.approved:
            self._state = TunerState.IDLE
            return TuningSessionResult(
                tuning_id="",
                strategy_id=strategy_id,
                tier=tier,
                status=TuningStatus.REJECTED,
                changes=[],
                eval_metrics=evaluation.metrics,
                reason=optimization.decision.reason,
            )

        # ── Step 3: Apply ──
        self._state = TunerState.APPLYING
        try:
            apply_result = await self._applier.apply(
                strategy_id=strategy_id,
                optimization=optimization,
                evaluation=evaluation,
                signal_generator=signal_gen,
                risk_engine=risk_engine,
                regime_switch_manager=regime_mgr,
            )
        except Exception:
            logger.exception("Apply failed for %s", strategy_id)
            self._state = TunerState.IDLE
            return TuningSessionResult(
                tuning_id="",
                strategy_id=strategy_id,
                tier=tier,
                status=TuningStatus.REJECTED,
                changes=[],
                eval_metrics=evaluation.metrics,
                reason="apply_error",
            )

        # ── Step 4: Enter monitoring (or pending) ──
        if apply_result.status == TuningStatus.MONITORING:
            self._state = TunerState.MONITORING
        else:
            self._state = TunerState.IDLE

        return TuningSessionResult(
            tuning_id=apply_result.tuning_id,
            strategy_id=strategy_id,
            tier=tier,
            status=apply_result.status,
            changes=apply_result.changes,
            eval_metrics=evaluation.metrics,
            reason="tuning_applied" if apply_result.status == TuningStatus.MONITORING else "pending_approval",
        )

    async def run_scheduled_tuning(
        self,
        strategy_ids: list[str] | None = None,
    ) -> list[TuningSessionResult]:
        """Run scheduled tuning for all active strategies.

        Tier determination:
        - Every week: Tier 1
        - Every 2 weeks: Tier 1 + Tier 2
        - Every 4 weeks: Tier 1 + Tier 2 + Tier 3
        """
        if strategy_ids is None:
            strategy_ids = list(self._strategies.keys())

        now = datetime.now(tz=timezone.utc)
        week_num = now.isocalendar()[1]

        tiers = [TierLevel.TIER_1]
        if week_num % self._config.schedule.tier2_interval_weeks == 0:
            tiers.append(TierLevel.TIER_2)
        if week_num % self._config.schedule.tier3_interval_weeks == 0:
            tiers.append(TierLevel.TIER_3)

        results: list[TuningSessionResult] = []
        for sid in strategy_ids:
            for tier in tiers:
                result = await self.run_tuning_session(sid, tier)
                results.append(result)

        return results

    async def check_monitoring(self) -> None:
        """Check all active monitoring sessions. Called hourly by scheduler."""
        sessions = await self._store.get_monitoring_sessions()

        for record in sessions:
            components = self._strategies.get(record.strategy_id, {})
            if not components:
                continue

            result = await self._rollback.check(
                tuning_id=record.tuning_id,
                strategy_id=record.strategy_id,
                signal_generator=components.get("signal_generator"),
                risk_engine=components.get("risk_engine"),
                regime_switch_manager=components.get("regime_switch_manager"),
            )

            if result.action == "suspend":
                self._state = TunerState.SUSPENDED
                logger.warning("Tuner suspended: %s", result.reason)
                await self._notify(f"[AI Tuner] 튜너 일시 중단: {result.reason}")
            elif result.action == "confirm":
                logger.info("Tuning %s confirmed", record.tuning_id)
            elif result.action == "rollback":
                logger.warning("Tuning %s rolled back: %s", record.tuning_id, result.reason)

    async def manual_rollback(self, tuning_id: str) -> bool:
        """Manual rollback triggered via API or Telegram."""
        records = await self._store.get_tuning_history(limit=200)
        for r in records:
            if r.tuning_id == tuning_id:
                components = self._strategies.get(r.strategy_id, {})
                return await self._applier.rollback(
                    tuning_id,
                    components.get("signal_generator"),
                    components.get("risk_engine"),
                    components.get("regime_switch_manager"),
                    reason="manual_rollback",
                )
        return False

    async def approve_tier3(self, tuning_id: str, approved: bool) -> bool:
        """Approve or reject a Tier 3 pending change."""
        if approved:
            # Find the record and apply
            records = await self._store.get_tuning_history(
                status=TuningStatus.PENDING,
            )
            for r in records:
                if r.tuning_id == tuning_id:
                    components = self._strategies.get(r.strategy_id, {})
                    sg = components.get("signal_generator")
                    if sg:
                        self._applier._apply_to_components(
                            r.changes, sg,
                            components.get("risk_engine"),
                            components.get("regime_switch_manager"),
                        )
                    await self._store.update_tuning_status(tuning_id, TuningStatus.MONITORING)
                    return True
        else:
            await self._store.update_tuning_status(tuning_id, TuningStatus.REJECTED)
            return True
        return False

    # ── Internal helpers ──

    def _get_eval_days(self, tier: TierLevel) -> int:
        sched = self._config.schedule
        if tier == TierLevel.TIER_1:
            return sched.tier1_eval_days
        if tier == TierLevel.TIER_2:
            return sched.tier2_eval_days
        return sched.tier3_eval_days

    def _extract_current_params(
        self,
        signal_gen: object,
        risk_engine: object | None,
        tier: TierLevel,
    ) -> dict[str, float]:
        """Extract current parameter values from live components."""
        from engine.tuner.config import get_bounds_for_tier

        params: dict[str, float] = {}
        bounds = get_bounds_for_tier(tier)

        for b in bounds:
            val = self._applier._get_current_value(b.name, signal_gen, risk_engine)
            if val is not None:
                params[b.name] = val

        return params

    async def _fetch_ohlcv(
        self,
        strategy_id: str,
        components: dict,
    ) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV data for optimization."""
        exchange = components.get("exchange_client")
        if not exchange:
            logger.warning("No exchange client for %s, returning empty OHLCV", strategy_id)
            return {}

        ohlcv_by_tf: dict[str, pd.DataFrame] = {}
        total_bars = self._config.guardrails.wf_train_bars + self._config.guardrails.wf_test_bars

        for tf in ["1h", "4h"]:
            try:
                candles = await exchange.fetch_ohlcv(  # type: ignore[attr-defined]
                    "BTC/KRW", tf, limit=total_bars,
                )
                if candles:
                    ohlcv_by_tf[tf] = pd.DataFrame(
                        candles, columns=["timestamp", "open", "high", "low", "close", "volume"],
                    )
            except Exception:
                logger.exception("Failed to fetch %s OHLCV for %s", tf, strategy_id)

        return ohlcv_by_tf

    async def _notify(self, message: str) -> None:
        if self._notifier and hasattr(self._notifier, "send_message"):
            try:
                await self._notifier.send_message(message)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("Notification failed")
