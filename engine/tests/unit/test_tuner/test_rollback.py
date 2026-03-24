"""Tests for engine.tuner.rollback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from engine.data.sqlite_store import SqliteDataStore
from engine.tuner.config import GuardrailSettings
from engine.tuner.enums import LLMConfidence, LLMProviderName, TierLevel, TuningStatus
from engine.tuner.models import (
    EvalMetrics,
    ParameterChange,
    RollbackCheckResult,
    TuningHistoryRecord,
)
from engine.tuner.rollback import RollbackMonitor
from engine.tuner.store import TunerStore


async def _setup() -> tuple[RollbackMonitor, TunerStore, SqliteDataStore]:
    ds = SqliteDataStore(":memory:")
    await ds.connect()
    ts = TunerStore(ds)

    applier = MagicMock()
    applier.rollback = AsyncMock(return_value=True)

    config = GuardrailSettings(
        monitoring_hours=48,
        mdd_rollback_multiplier=2.0,
        consecutive_loss_rollback=5,
        max_consecutive_rollbacks=3,
    )

    monitor = RollbackMonitor(
        data_store=ds,
        tuner_store=ts,
        applier=applier,
        notifier=None,
        config=config,
    )
    return monitor, ts, ds


def _make_monitoring_record(
    tuning_id: str = "tune-001",
    created_at: datetime | None = None,
    eval_mdd: float = 0.03,
) -> TuningHistoryRecord:
    return TuningHistoryRecord(
        tuning_id=tuning_id,
        created_at=created_at or datetime.now(tz=timezone.utc),
        strategy_id="STR-001",
        changes=[
            ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20),
        ],
        eval_metrics=EvalMetrics(
            strategy_id="STR-001",
            eval_window="2026-03-13~2026-03-20",
            regime="RANGING_LOW_VOL",
            total_trades=10,
            win_rate=0.40,
            profit_factor=1.2,
            max_drawdown=eval_mdd,
            avg_r_multiple=0.8,
            signal_accuracy=0.35,
            avg_holding_hours=6.0,
            total_return_pct=0.01,
            sharpe_ratio=0.4,
        ),
        validation_pf=1.5,
        validation_mdd=0.02,
        llm_provider=LLMProviderName.DEGRADED,
        llm_model=None,
        llm_diagnosis=None,
        llm_confidence=None,
        reason="test",
        status=TuningStatus.MONITORING,
    )


class TestRollbackMonitor:
    async def test_continue_during_monitoring(self):
        """Within monitoring window, no issues → continue."""
        monitor, ts, _ = await _setup()
        now = datetime.now(tz=timezone.utc)
        record = _make_monitoring_record(created_at=now)
        await ts.save_tuning_history(record)

        result = await monitor.check(
            "tune-001", "STR-001", MagicMock(),
        )
        assert result.action == "continue"

    async def test_confirm_after_monitoring_period(self):
        """Monitoring period complete, no issues → confirm."""
        monitor, ts, _ = await _setup()
        # Set created_at to 49 hours ago (past 48h monitoring)
        past = datetime.now(tz=timezone.utc) - timedelta(hours=49)
        record = _make_monitoring_record(created_at=past)
        await ts.save_tuning_history(record)

        result = await monitor.check(
            "tune-001", "STR-001", MagicMock(),
        )
        assert result.action == "confirm"

        # Verify status updated to CONFIRMED
        history = await ts.get_tuning_history(status=TuningStatus.CONFIRMED)
        assert len(history) == 1

    async def test_record_not_found(self):
        monitor, _, _ = await _setup()
        result = await monitor.check(
            "nonexistent", "STR-001", MagicMock(),
        )
        assert result.action == "continue"
        assert result.reason == "record_not_found"


class TestCalculateMDD:
    def test_basic_mdd(self):
        pnls = [100, 200, -150, -100, 50]
        mdd = RollbackMonitor._calculate_mdd(pnls)
        assert mdd > 0

    def test_no_drawdown(self):
        pnls = [100, 100, 100]
        mdd = RollbackMonitor._calculate_mdd(pnls)
        assert mdd == 0.0

    def test_empty_pnls(self):
        assert RollbackMonitor._calculate_mdd([]) == 0.0


class TestConsecutiveRollbacks:
    async def test_rollback_count_increments(self):
        monitor, _, _ = await _setup()
        assert monitor.consecutive_rollback_count == 0
        monitor._consecutive_rollback_count = 2
        assert monitor.consecutive_rollback_count == 2

    async def test_reset_rollback_count(self):
        monitor, _, _ = await _setup()
        monitor._consecutive_rollback_count = 3
        monitor.reset_rollback_count()
        assert monitor.consecutive_rollback_count == 0
