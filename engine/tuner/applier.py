"""ParameterApplier — hot-reload strategy parameters + history + rollback.

Applies optimized parameters to running SignalGenerator, RiskEngine,
and RegimeSwitchManager instances without restart.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace as dc_replace
from datetime import datetime, timedelta, timezone

from engine.tuner.enums import LLMProviderName, TierLevel, TuningStatus
from engine.tuner.guardrails import Guardrails
from engine.tuner.models import (
    ApplyResult,
    EvalMetrics,
    EvaluationResult,
    OptimizationResult,
    ParameterChange,
    TuningHistoryRecord,
)
from engine.tuner.store import TunerStore

logger = logging.getLogger(__name__)


class ParameterApplier:
    """Parameter hot-reload + history persistence + rollback."""

    def __init__(
        self,
        tuner_store: TunerStore,
        guardrails: Guardrails,
        notifier: object | None = None,
        monitoring_hours: int = 48,
    ) -> None:
        self._store = tuner_store
        self._guardrails = guardrails
        self._notifier = notifier
        self._monitoring_hours = monitoring_hours

    async def apply(
        self,
        strategy_id: str,
        optimization: OptimizationResult,
        evaluation: EvaluationResult,
        signal_generator: object,
        risk_engine: object | None = None,
        regime_switch_manager: object | None = None,
    ) -> ApplyResult:
        """Apply optimized parameters with guardrail validation.

        1. Build ParameterChanges from selected candidate vs current
        2. Guardrails.validate_changes() → clamp + violation check
        3. If requires_approval → status=PENDING, return
        4. Apply Tier 1/2/3 parameters to live components
        5. Save tuning_history(status=MONITORING)
        6. Telegram notification
        7. Return ApplyResult with monitoring_until
        """
        candidate = optimization.selected
        if candidate is None:
            return ApplyResult(
                tuning_id="",
                changes=[],
                status=TuningStatus.REJECTED,
                monitoring_until=None,
            )

        # Build changes
        changes = self._build_changes(candidate.params, signal_generator, risk_engine)

        # Guardrails validation
        guard_result = await self._guardrails.validate_changes(changes, strategy_id)
        clamped = guard_result.clamped_changes

        if guard_result.violations:
            for v in guard_result.violations:
                logger.warning("Guardrail violation: %s", v)

        if not guard_result.passed:
            return ApplyResult(
                tuning_id="",
                changes=clamped,
                status=TuningStatus.REJECTED,
                monitoring_until=None,
            )

        now = datetime.now(tz=timezone.utc)
        tuning_id = f"tune-{strategy_id}-{now.strftime('%Y%m%d%H%M%S')}"

        # Tier 3 requires approval
        if guard_result.requires_approval:
            record = self._build_history_record(
                tuning_id, strategy_id, clamped, evaluation,
                optimization, TuningStatus.PENDING, now,
            )
            await self._store.save_tuning_history(record)
            await self._notify(
                f"[AI Tuner] {strategy_id} Tier 3 변경 승인 대기\n"
                + self._format_changes(clamped),
            )
            return ApplyResult(
                tuning_id=tuning_id,
                changes=clamped,
                status=TuningStatus.PENDING,
                monitoring_until=None,
            )

        # Apply parameters
        self._apply_to_components(clamped, signal_generator, risk_engine, regime_switch_manager)

        # Save history
        monitoring_until = now + timedelta(hours=self._monitoring_hours)
        record = self._build_history_record(
            tuning_id, strategy_id, clamped, evaluation,
            optimization, TuningStatus.MONITORING, now,
        )
        await self._store.save_tuning_history(record)

        # Notify
        provider = optimization.decision.provider.value if optimization.decision else "unknown"
        model = optimization.decision.model if optimization.decision else None
        await self._notify(
            f"[AI Tuner] {strategy_id} 파라미터 적용 (모니터링 {self._monitoring_hours}h)\n"
            f"Provider: {provider}" + (f" ({model})" if model else "") + "\n"
            + self._format_changes(clamped),
        )

        return ApplyResult(
            tuning_id=tuning_id,
            changes=clamped,
            status=TuningStatus.MONITORING,
            monitoring_until=monitoring_until,
        )

    async def rollback(
        self,
        tuning_id: str,
        signal_generator: object,
        risk_engine: object | None = None,
        regime_switch_manager: object | None = None,
        reason: str = "auto_rollback",
    ) -> bool:
        """Rollback to old parameter values.

        1. Get tuning_history for tuning_id
        2. Restore each parameter to old_value
        3. Update status to ROLLED_BACK
        4. Telegram notification
        """
        records = await self._store.get_tuning_history(limit=100)
        target = None
        for r in records:
            if r.tuning_id == tuning_id:
                target = r
                break

        if target is None:
            logger.warning("Rollback failed: tuning_id %s not found", tuning_id)
            return False

        # Build rollback changes (swap old and new)
        rollback_changes = [
            ParameterChange(
                parameter_name=c.parameter_name,
                tier=c.tier,
                old_value=c.new_value,
                new_value=c.old_value,
                change_pct=-c.change_pct,
            )
            for c in target.changes
        ]

        self._apply_to_components(
            rollback_changes, signal_generator, risk_engine, regime_switch_manager,
        )

        await self._store.update_tuning_status(
            tuning_id, TuningStatus.ROLLED_BACK,
            rollback_at=datetime.now(tz=timezone.utc),
        )

        await self._notify(
            f"[AI Tuner] {target.strategy_id} 롤백 완료 ({reason})\n"
            + self._format_changes(rollback_changes),
        )

        logger.info("Rolled back tuning %s for %s: %s", tuning_id, target.strategy_id, reason)
        return True

    # ── Internal helpers ──

    def _build_changes(
        self,
        params: dict[str, float],
        signal_generator: object,
        risk_engine: object | None,
    ) -> list[ParameterChange]:
        """Build ParameterChange list from candidate params vs current values."""
        from engine.tuner.config import ALL_BOUNDS

        changes: list[ParameterChange] = []
        for name, new_val in params.items():
            bounds = ALL_BOUNDS.get(name)
            if not bounds:
                continue

            old_val = self._get_current_value(name, signal_generator, risk_engine)
            if old_val is None:
                continue

            change_pct = (new_val - old_val) / abs(old_val) if old_val != 0 else 0.0
            changes.append(ParameterChange(
                parameter_name=name,
                tier=bounds.tier,
                old_value=old_val,
                new_value=new_val,
                change_pct=change_pct,
            ))

        return changes

    def _get_current_value(
        self,
        param_name: str,
        signal_generator: object,
        risk_engine: object | None,
    ) -> float | None:
        """Get current parameter value from live components."""
        # Tier 1: SignalGenerator
        sg = signal_generator
        if param_name == "buy_threshold":
            return getattr(sg, "buy_threshold", None)
        if param_name == "sell_threshold":
            return getattr(sg, "sell_threshold", None)
        if param_name == "macro_weight":
            return getattr(sg, "macro_weight", None)
        if param_name.startswith("tf_weight_"):
            tf_key = param_name.replace("tf_weight_", "")
            tf_weights = getattr(sg, "tf_weights", {})
            return tf_weights.get(tf_key)
        if param_name.startswith("score_w"):
            sw = getattr(sg, "score_weights", None)
            idx = param_name[-1]  # "score_w1" -> "1"
            return getattr(sw, f"w{idx}", None) if sw else None

        # Tier 2: RiskEngine
        if risk_engine:
            config = getattr(risk_engine, "config", None)
            if config and hasattr(config, param_name):
                return getattr(config, param_name)

        return None

    def _apply_to_components(
        self,
        changes: list[ParameterChange],
        signal_generator: object,
        risk_engine: object | None,
        regime_switch_manager: object | None,
    ) -> None:
        """Apply parameter changes to live components."""
        from dataclasses import replace

        tier2_overrides: dict[str, float] = {}
        tier3_overrides: dict[str, float] = {}

        for change in changes:
            name = change.parameter_name
            val = change.new_value

            if change.tier == TierLevel.TIER_1:
                self._apply_tier1(signal_generator, name, val)
            elif change.tier == TierLevel.TIER_2:
                tier2_overrides[name] = val
            elif change.tier == TierLevel.TIER_3:
                tier3_overrides[name] = val

        # Tier 2: replace frozen RiskConfig
        if tier2_overrides and risk_engine:
            config = getattr(risk_engine, "config", None)
            if config:
                new_config = replace(config, **tier2_overrides)
                risk_engine.config = new_config  # type: ignore[attr-defined]
                logger.info("Applied Tier 2 params: %s", list(tier2_overrides.keys()))

        # Tier 3: update RegimeSwitchManager config
        if tier3_overrides and regime_switch_manager:
            config = getattr(regime_switch_manager, "config", None)
            if config:
                new_config = replace(config, **{
                    k: int(v) if k in ("debounce_count", "cooldown_minutes") else v
                    for k, v in tier3_overrides.items()
                })
                regime_switch_manager.config = new_config  # type: ignore[attr-defined]
                logger.info("Applied Tier 3 params: %s", list(tier3_overrides.keys()))

    def _apply_tier1(self, signal_generator: object, name: str, value: float) -> None:
        """Apply a single Tier 1 parameter to SignalGenerator."""
        sg = signal_generator
        if name == "buy_threshold":
            sg.buy_threshold = value  # type: ignore[attr-defined]
        elif name == "sell_threshold":
            sg.sell_threshold = value  # type: ignore[attr-defined]
        elif name == "macro_weight":
            sg.macro_weight = value  # type: ignore[attr-defined]
        elif name.startswith("tf_weight_"):
            tf_key = name.replace("tf_weight_", "")
            tf = dict(getattr(sg, "tf_weights", {}))
            tf[tf_key] = value
            sg.tf_weights = tf  # type: ignore[attr-defined]
        elif name.startswith("score_w"):
            from engine.strategy.scoring import ScoreWeights

            sw = getattr(sg, "score_weights", None)
            idx = name[-1]
            kwargs = {
                "w1": getattr(sw, "w1", 0.4) if sw else 0.4,
                "w2": getattr(sw, "w2", 0.3) if sw else 0.3,
                "w3": getattr(sw, "w3", 0.3) if sw else 0.3,
            }
            kwargs[f"w{idx}"] = value
            sg.score_weights = ScoreWeights(**kwargs)  # type: ignore[attr-defined]

        logger.debug("Applied Tier 1: %s = %s", name, value)

    def _build_history_record(
        self,
        tuning_id: str,
        strategy_id: str,
        changes: list[ParameterChange],
        evaluation: EvaluationResult,
        optimization: OptimizationResult,
        status: TuningStatus,
        now: datetime,
    ) -> TuningHistoryRecord:
        """Build a TuningHistoryRecord for DB persistence."""
        decision = optimization.decision
        return TuningHistoryRecord(
            tuning_id=tuning_id,
            created_at=now,
            strategy_id=strategy_id,
            changes=changes,
            eval_metrics=evaluation.metrics,
            validation_pf=optimization.selected.validation_pf if optimization.selected else None,
            validation_mdd=optimization.selected.validation_mdd if optimization.selected else None,
            llm_provider=decision.provider if decision else LLMProviderName.DEGRADED,
            llm_model=decision.model if decision else None,
            llm_diagnosis=None,
            llm_confidence=None,
            reason=decision.reason if decision else "",
            status=status,
        )

    def _format_changes(self, changes: list[ParameterChange]) -> str:
        """Format changes for notification message."""
        lines = []
        for c in changes:
            direction = "↑" if c.new_value > c.old_value else "↓"
            lines.append(f"  {c.parameter_name}: {c.old_value:.4f} → {c.new_value:.4f} {direction}")
        return "\n".join(lines)

    async def _notify(self, message: str) -> None:
        """Send notification via Telegram if available."""
        if self._notifier and hasattr(self._notifier, "send_message"):
            try:
                await self._notifier.send_message(message)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("Failed to send tuning notification")
