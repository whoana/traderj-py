"""RollbackMonitor — 48-hour monitoring + auto-rollback.

Periodically checks active tuning sessions and triggers rollback
if performance degrades beyond thresholds.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from engine.tuner.config import GuardrailSettings
from engine.tuner.enums import TuningStatus
from engine.tuner.models import RollbackCheckResult
from engine.tuner.store import TunerStore

logger = logging.getLogger(__name__)


class RollbackMonitor:
    """48-hour monitoring + auto-rollback for applied tuning changes."""

    def __init__(
        self,
        data_store: object,
        tuner_store: TunerStore,
        applier: object,  # ParameterApplier (forward ref to avoid circular)
        notifier: object | None,
        config: GuardrailSettings,
    ) -> None:
        self._data_store = data_store
        self._tuner_store = tuner_store
        self._applier = applier
        self._notifier = notifier
        self._config = config
        self._consecutive_rollback_count: int = 0

    async def check(
        self,
        tuning_id: str,
        strategy_id: str,
        signal_generator: object,
        risk_engine: object | None = None,
        regime_switch_manager: object | None = None,
    ) -> RollbackCheckResult:
        """Check a monitoring session and decide action.

        Called hourly for each active monitoring session.

        Returns:
            RollbackCheckResult with action:
            - "continue": still within monitoring window, no issues
            - "confirm": monitoring complete, performance acceptable
            - "rollback": performance degraded, rolling back
            - "suspend": too many consecutive rollbacks, suspending tuner
        """
        # Get the tuning record
        records = await self._tuner_store.get_tuning_history(
            strategy_id=strategy_id, status=TuningStatus.MONITORING,
        )
        target = None
        for r in records:
            if r.tuning_id == tuning_id:
                target = r
                break

        if target is None:
            return RollbackCheckResult(action="continue", reason="record_not_found")

        now = datetime.now(tz=timezone.utc)
        applied_at = target.created_at
        monitoring_until = applied_at + timedelta(hours=self._config.monitoring_hours)

        # Get post-tuning performance
        post_metrics = await self._get_post_tuning_metrics(strategy_id, applied_at)

        eval_mdd = target.eval_metrics.max_drawdown
        current_mdd = post_metrics.get("max_drawdown", 0.0)
        consecutive_losses = post_metrics.get("consecutive_losses", 0)

        # Check rollback conditions
        mdd_threshold = eval_mdd * self._config.mdd_rollback_multiplier
        should_rollback = False
        rollback_reason = ""

        if mdd_threshold > 0 and current_mdd > mdd_threshold:
            should_rollback = True
            rollback_reason = (
                f"MDD {current_mdd:.2%} > threshold {mdd_threshold:.2%} "
                f"(eval_mdd={eval_mdd:.2%} x {self._config.mdd_rollback_multiplier})"
            )

        if consecutive_losses >= self._config.consecutive_loss_rollback:
            should_rollback = True
            rollback_reason = (
                f"Consecutive losses {consecutive_losses} >= "
                f"threshold {self._config.consecutive_loss_rollback}"
            )

        if should_rollback:
            # Perform rollback
            success = await self._applier.rollback(  # type: ignore[attr-defined]
                tuning_id, signal_generator, risk_engine,
                regime_switch_manager, reason=rollback_reason,
            )
            if success:
                self._consecutive_rollback_count += 1

                # Check if we should suspend
                if self._consecutive_rollback_count >= self._config.max_consecutive_rollbacks:
                    return RollbackCheckResult(
                        action="suspend",
                        reason=(
                            f"Consecutive rollbacks ({self._consecutive_rollback_count}) "
                            f">= max ({self._config.max_consecutive_rollbacks})"
                        ),
                    )

                return RollbackCheckResult(action="rollback", reason=rollback_reason)
            return RollbackCheckResult(action="continue", reason="rollback_failed")

        # Check if monitoring period is complete
        if now >= monitoring_until:
            await self._tuner_store.update_tuning_status(tuning_id, TuningStatus.CONFIRMED)
            self._consecutive_rollback_count = 0  # Reset on success
            logger.info("Tuning %s confirmed after %dh monitoring", tuning_id, self._config.monitoring_hours)
            return RollbackCheckResult(
                action="confirm",
                reason=f"Monitoring complete ({self._config.monitoring_hours}h), performance acceptable",
            )

        return RollbackCheckResult(action="continue", reason="monitoring_in_progress")

    async def _get_post_tuning_metrics(
        self,
        strategy_id: str,
        since: datetime,
    ) -> dict[str, float]:
        """Get performance metrics since tuning was applied."""
        try:
            positions = await self._data_store.get_positions(  # type: ignore[attr-defined]
                strategy_id=strategy_id,
            )
            post_positions = [
                p for p in positions
                if hasattr(p, "opened_at") and p.opened_at and p.opened_at >= since
            ]

            if not post_positions:
                return {"max_drawdown": 0.0, "consecutive_losses": 0}

            # Calculate consecutive losses from most recent
            consecutive = 0
            for p in reversed(post_positions):
                if hasattr(p, "realized_pnl") and float(p.realized_pnl) <= 0:
                    consecutive += 1
                else:
                    break

            # Simple MDD from PnLs
            pnls = [
                float(p.realized_pnl) for p in post_positions
                if hasattr(p, "realized_pnl") and hasattr(p, "status")
                and str(p.status) == "closed"
            ]
            mdd = self._calculate_mdd(pnls) if pnls else 0.0

            return {
                "max_drawdown": mdd,
                "consecutive_losses": consecutive,
            }
        except Exception:
            logger.exception("Failed to get post-tuning metrics for %s", strategy_id)
            return {"max_drawdown": 0.0, "consecutive_losses": 0}

    @staticmethod
    def _calculate_mdd(pnls: list[float]) -> float:
        """Calculate max drawdown from a sequence of PnLs."""
        if not pnls:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for pnl in pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / max(abs(peak), 1.0) if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        return max_dd

    @property
    def active_sessions(self) -> list[str]:
        """List of tuning IDs currently being monitored (sync accessor)."""
        # This is populated by check_monitoring in the pipeline
        return []

    @property
    def consecutive_rollback_count(self) -> int:
        return self._consecutive_rollback_count

    def reset_rollback_count(self) -> None:
        self._consecutive_rollback_count = 0
