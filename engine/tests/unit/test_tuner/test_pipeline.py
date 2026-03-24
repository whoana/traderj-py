"""Tests for engine.tuner.pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from engine.strategy.signal import SignalGenerator
from engine.tuner.config import TunerSettings
from engine.tuner.enums import TierLevel, TunerState, TuningStatus
from engine.tuner.models import (
    ApplyResult,
    EvalMetrics,
    EvaluationResult,
    OptimizerCandidate,
    OptimizationResult,
    ParameterChange,
    TuningDecision,
    TuningSessionResult,
)
from engine.tuner.pipeline import TunerPipeline


def _mock_pipeline() -> TunerPipeline:
    evaluator = MagicMock()
    optimizer = MagicMock()
    applier = MagicMock()
    rollback = MagicMock()
    store = MagicMock()
    config = TunerSettings()

    pipeline = TunerPipeline(
        evaluator=evaluator,
        optimizer=optimizer,
        applier=applier,
        rollback_monitor=rollback,
        tuner_store=store,
        notifier=None,
        config=config,
    )
    return pipeline


def _eval_result(should_tune: bool = True) -> EvaluationResult:
    return EvaluationResult(
        metrics=EvalMetrics(
            strategy_id="STR-001",
            eval_window="2026-03-13~2026-03-20",
            regime="RANGING_LOW_VOL",
            total_trades=10,
            win_rate=0.40,
            profit_factor=1.2,
            max_drawdown=0.03,
            avg_r_multiple=0.8,
            signal_accuracy=0.35,
            avg_holding_hours=6.0,
            total_return_pct=0.01,
            sharpe_ratio=0.4,
        ),
        diagnosis=None,
        rule_diagnosis=[],
        should_tune=should_tune,
        skip_reason=None if should_tune else "metrics_acceptable",
    )


def _opt_result(approved: bool = True) -> OptimizationResult:
    candidate = OptimizerCandidate(
        candidate_id="C-001",
        params={"buy_threshold": 0.12},
        validation_pf=1.5,
        validation_mdd=0.02,
        validation_win_rate=0.5,
        validation_trades=10,
        optuna_trial_number=1,
    )
    from engine.tuner.enums import LLMProviderName

    return OptimizationResult(
        candidates=[candidate],
        selected=candidate if approved else None,
        decision=TuningDecision(
            approved=approved,
            selected_candidate=candidate if approved else None,
            reason="good" if approved else "rejected",
            provider=LLMProviderName.DEGRADED,
            model=None,
        ),
    )


class TestTunerPipelineState:
    def test_initial_state_idle(self):
        pipeline = _mock_pipeline()
        assert pipeline.state == TunerState.IDLE

    async def test_suspended_skips_session(self):
        pipeline = _mock_pipeline()
        pipeline._state = TunerState.SUSPENDED
        sig_gen = SignalGenerator(strategy_id="STR-001")
        pipeline.register_strategy("STR-001", sig_gen)

        result = await pipeline.run_tuning_session("STR-001")
        assert result.status == TuningStatus.REJECTED
        assert result.reason == "tuner_suspended"

    async def test_unregistered_strategy_rejected(self):
        pipeline = _mock_pipeline()
        result = await pipeline.run_tuning_session("UNKNOWN")
        assert result.status == TuningStatus.REJECTED
        assert result.reason == "strategy_not_registered"


class TestTuningSession:
    async def test_skip_when_no_tuning_needed(self):
        pipeline = _mock_pipeline()
        sig_gen = SignalGenerator(strategy_id="STR-001")
        pipeline.register_strategy("STR-001", sig_gen)

        pipeline._evaluator.evaluate = AsyncMock(return_value=_eval_result(should_tune=False))

        result = await pipeline.run_tuning_session("STR-001")
        assert result.status == TuningStatus.REJECTED
        assert pipeline.state == TunerState.IDLE

    async def test_skip_when_optimization_rejected(self):
        pipeline = _mock_pipeline()
        sig_gen = SignalGenerator(strategy_id="STR-001")
        pipeline.register_strategy("STR-001", sig_gen)

        pipeline._evaluator.evaluate = AsyncMock(return_value=_eval_result(should_tune=True))
        pipeline._optimizer.optimize = AsyncMock(return_value=_opt_result(approved=False))

        result = await pipeline.run_tuning_session("STR-001")
        assert result.status == TuningStatus.REJECTED

    async def test_full_session_success(self):
        pipeline = _mock_pipeline()
        sig_gen = SignalGenerator(strategy_id="STR-001", buy_threshold=0.10)
        pipeline.register_strategy("STR-001", sig_gen)

        pipeline._evaluator.evaluate = AsyncMock(return_value=_eval_result(should_tune=True))
        pipeline._optimizer.optimize = AsyncMock(return_value=_opt_result(approved=True))
        pipeline._applier.apply = AsyncMock(return_value=ApplyResult(
            tuning_id="tune-001",
            changes=[ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20)],
            status=TuningStatus.MONITORING,
            monitoring_until=None,
        ))

        result = await pipeline.run_tuning_session("STR-001")
        assert result.status == TuningStatus.MONITORING
        assert result.tuning_id == "tune-001"
        assert pipeline.state == TunerState.MONITORING


class TestRegisterStrategy:
    def test_register_and_lookup(self):
        pipeline = _mock_pipeline()
        sig_gen = SignalGenerator(strategy_id="STR-001")
        pipeline.register_strategy("STR-001", sig_gen)
        assert "STR-001" in pipeline._strategies
        assert pipeline._strategies["STR-001"]["signal_generator"] is sig_gen


class TestCheckMonitoring:
    async def test_check_calls_rollback_monitor(self):
        pipeline = _mock_pipeline()
        pipeline._store.get_monitoring_sessions = AsyncMock(return_value=[])
        await pipeline.check_monitoring()
        pipeline._store.get_monitoring_sessions.assert_called_once()
