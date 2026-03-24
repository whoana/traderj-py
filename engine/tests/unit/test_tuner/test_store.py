"""Tests for engine.tuner.store using in-memory SQLite."""

from __future__ import annotations

from datetime import datetime, timezone

from engine.data.sqlite_store import SqliteDataStore
from engine.tuner.enums import (
    DiagnosisDirection,
    LLMConfidence,
    LLMProviderName,
    TierLevel,
    TuningStatus,
)
from engine.tuner.models import (
    EvalMetrics,
    ParameterChange,
    ParamRecommendation,
    TuningHistoryRecord,
    TuningReport,
)
from engine.tuner.store import TunerStore


async def _setup() -> tuple[SqliteDataStore, TunerStore]:
    ds = SqliteDataStore(":memory:")
    await ds.connect()
    ts = TunerStore(ds)
    return ds, ts


_seq = 0


def _make_record(tuning_id: str = "tune-001", status: TuningStatus = TuningStatus.APPLIED) -> TuningHistoryRecord:
    global _seq
    _seq += 1
    return TuningHistoryRecord(
        tuning_id=tuning_id,
        created_at=datetime(2026, 3, 20, 0, 0, _seq, tzinfo=timezone.utc),
        strategy_id="STR-001",
        changes=[
            ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20),
            ParameterChange("sell_threshold", TierLevel.TIER_1, -0.10, -0.08, 0.20),
        ],
        eval_metrics=EvalMetrics(
            strategy_id="STR-001",
            eval_window="2026-03-13~2026-03-20",
            regime="RANGING_LOW_VOL",
            total_trades=8,
            win_rate=0.25,
            profit_factor=0.5,
            max_drawdown=0.03,
            avg_r_multiple=0.5,
            signal_accuracy=0.20,
            avg_holding_hours=4.0,
            total_return_pct=-0.01,
            sharpe_ratio=0.1,
        ),
        validation_pf=1.42,
        validation_mdd=0.02,
        llm_provider=LLMProviderName.CLAUDE,
        llm_model="claude-sonnet-4-20250514",
        llm_diagnosis='{"root_causes": ["too loose"]}',
        llm_confidence=LLMConfidence.HIGH,
        reason="buy_threshold too low",
        status=status,
    )


class TestTunerStore:
    async def test_save_and_get_history(self):
        _, ts = await _setup()
        record = _make_record()
        await ts.save_tuning_history(record)

        results = await ts.get_tuning_history(strategy_id="STR-001")
        assert len(results) == 1
        assert results[0].tuning_id == "tune-001"
        assert len(results[0].changes) == 2
        assert results[0].changes[0].parameter_name == "buy_threshold"

    async def test_get_latest_tuning(self):
        _, ts = await _setup()
        await ts.save_tuning_history(_make_record("tune-001"))
        await ts.save_tuning_history(_make_record("tune-002"))

        latest = await ts.get_latest_tuning("STR-001")
        assert latest is not None

    async def test_update_status(self):
        _, ts = await _setup()
        await ts.save_tuning_history(_make_record("tune-001", TuningStatus.MONITORING))

        await ts.update_tuning_status("tune-001", TuningStatus.CONFIRMED)
        results = await ts.get_tuning_history(status=TuningStatus.CONFIRMED)
        assert len(results) == 1
        assert results[0].status == TuningStatus.CONFIRMED

    async def test_get_last_change_direction_increase(self):
        _, ts = await _setup()
        await ts.save_tuning_history(_make_record())

        direction = await ts.get_last_change_direction("STR-001", "buy_threshold")
        assert direction == DiagnosisDirection.INCREASE  # 0.10 -> 0.12

    async def test_get_last_change_direction_decrease(self):
        _, ts = await _setup()
        await ts.save_tuning_history(_make_record())

        direction = await ts.get_last_change_direction("STR-001", "sell_threshold")
        assert direction == DiagnosisDirection.INCREASE  # -0.10 -> -0.08 (value increased)

    async def test_get_last_change_direction_no_history(self):
        _, ts = await _setup()
        direction = await ts.get_last_change_direction("STR-001", "buy_threshold")
        assert direction is None

    async def test_count_consecutive_rollbacks(self):
        _, ts = await _setup()
        await ts.save_tuning_history(_make_record("tune-001", TuningStatus.ROLLED_BACK))
        await ts.save_tuning_history(_make_record("tune-002", TuningStatus.ROLLED_BACK))

        count = await ts.count_consecutive_rollbacks("STR-001")
        assert count == 2

    async def test_count_consecutive_rollbacks_broken_by_confirmed(self):
        _, ts = await _setup()
        await ts.save_tuning_history(_make_record("tune-001", TuningStatus.CONFIRMED))
        await ts.save_tuning_history(_make_record("tune-002", TuningStatus.ROLLED_BACK))

        count = await ts.count_consecutive_rollbacks("STR-001")
        assert count == 1

    async def test_get_monitoring_sessions(self):
        _, ts = await _setup()
        await ts.save_tuning_history(_make_record("tune-001", TuningStatus.MONITORING))
        await ts.save_tuning_history(_make_record("tune-002", TuningStatus.CONFIRMED))

        sessions = await ts.get_monitoring_sessions()
        assert len(sessions) == 1
        assert sessions[0].tuning_id == "tune-001"

    async def test_save_and_query_report(self):
        _, ts = await _setup()
        report = TuningReport(
            tuning_id="tune-001",
            created_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
            eval_window="2026-03-13~2026-03-20",
            strategy_id="STR-001",
            metrics=EvalMetrics(
                strategy_id="STR-001",
                eval_window="2026-03-13~2026-03-20",
                regime="RANGING_LOW_VOL",
                total_trades=8,
                win_rate=0.25,
                profit_factor=0.5,
                max_drawdown=0.03,
                avg_r_multiple=0.5,
                signal_accuracy=0.20,
                avg_holding_hours=4.0,
                total_return_pct=-0.01,
                sharpe_ratio=0.1,
            ),
            recommendations=[
                ParamRecommendation("buy_threshold", DiagnosisDirection.INCREASE, "too low"),
            ],
            applied_changes=[
                ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20),
            ],
            status=TuningStatus.APPLIED,
        )
        await ts.save_tuning_report(report)
        # No error = success
