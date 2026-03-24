"""Tests for engine.tuner.applier."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from engine.data.sqlite_store import SqliteDataStore
from engine.strategy.risk import RiskConfig
from engine.strategy.signal import SignalGenerator
from engine.tuner.applier import ParameterApplier
from engine.tuner.config import GuardrailSettings
from engine.tuner.enums import LLMProviderName, TierLevel, TuningStatus
from engine.tuner.guardrails import Guardrails
from engine.tuner.models import (
    EvalMetrics,
    EvaluationResult,
    OptimizerCandidate,
    OptimizationResult,
    ParameterChange,
    TuningDecision,
)
from engine.tuner.store import TunerStore


async def _setup() -> tuple[ParameterApplier, TunerStore, Guardrails]:
    ds = SqliteDataStore(":memory:")
    await ds.connect()
    ts = TunerStore(ds)
    config = GuardrailSettings()
    guardrails = Guardrails(config, ts)
    applier = ParameterApplier(ts, guardrails)
    return applier, ts, guardrails


def _make_eval() -> EvaluationResult:
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
        should_tune=True,
        skip_reason=None,
    )


def _make_optimization(params: dict[str, float] | None = None) -> OptimizationResult:
    p = params or {"buy_threshold": 0.12}
    candidate = OptimizerCandidate(
        candidate_id="C-001",
        params=p,
        validation_pf=1.5,
        validation_mdd=0.02,
        validation_win_rate=0.5,
        validation_trades=10,
        optuna_trial_number=1,
    )
    return OptimizationResult(
        candidates=[candidate],
        selected=candidate,
        decision=TuningDecision(
            approved=True,
            selected_candidate=candidate,
            reason="good",
            provider=LLMProviderName.DEGRADED,
            model=None,
        ),
    )


class TestApply:
    async def test_apply_tier1_changes(self):
        applier, ts, _ = await _setup()
        sig_gen = SignalGenerator(strategy_id="STR-001", buy_threshold=0.10, sell_threshold=-0.10)

        result = await applier.apply(
            strategy_id="STR-001",
            optimization=_make_optimization({"buy_threshold": 0.11}),
            evaluation=_make_eval(),
            signal_generator=sig_gen,
        )

        assert result.status == TuningStatus.MONITORING
        assert result.tuning_id != ""
        assert result.monitoring_until is not None
        # Verify parameter was applied
        assert sig_gen.buy_threshold == 0.11

    async def test_apply_no_candidate_rejected(self):
        applier, _, _ = await _setup()
        sig_gen = SignalGenerator(strategy_id="STR-001")

        opt = OptimizationResult(
            candidates=[],
            selected=None,
            decision=TuningDecision(
                approved=False, selected_candidate=None,
                reason="no_candidates", provider=LLMProviderName.DEGRADED, model=None,
            ),
        )

        result = await applier.apply("STR-001", opt, _make_eval(), sig_gen)
        assert result.status == TuningStatus.REJECTED

    async def test_apply_saves_history(self):
        applier, ts, _ = await _setup()
        sig_gen = SignalGenerator(strategy_id="STR-001", buy_threshold=0.10)

        await applier.apply(
            "STR-001",
            _make_optimization({"buy_threshold": 0.11}),
            _make_eval(),
            sig_gen,
        )

        history = await ts.get_tuning_history(strategy_id="STR-001")
        assert len(history) >= 1
        assert history[0].status == TuningStatus.MONITORING


class TestApplyTier1:
    async def test_apply_tf_weights(self):
        applier, _, _ = await _setup()
        sig_gen = SignalGenerator(
            strategy_id="STR-001",
            tf_weights={"1h": 0.3, "4h": 0.5},
        )

        applier._apply_tier1(sig_gen, "tf_weight_1h", 0.4)
        assert sig_gen.tf_weights["1h"] == 0.4
        assert sig_gen.tf_weights["4h"] == 0.5  # unchanged

    async def test_apply_score_weights(self):
        applier, _, _ = await _setup()
        sig_gen = SignalGenerator(strategy_id="STR-001")

        applier._apply_tier1(sig_gen, "score_w1", 0.5)
        assert sig_gen.score_weights.w1 == 0.5


class TestApplyTier2:
    async def test_apply_risk_config(self):
        applier, _, _ = await _setup()

        class FakeRiskEngine:
            def __init__(self):
                self.config = RiskConfig(atr_stop_multiplier=2.0)

        re = FakeRiskEngine()
        changes = [
            ParameterChange("atr_stop_multiplier", TierLevel.TIER_2, 2.0, 2.5, 0.25),
        ]
        applier._apply_to_components(changes, MagicMock(), re, None)
        assert re.config.atr_stop_multiplier == 2.5


class TestRollback:
    async def test_rollback_restores_old_values(self):
        applier, ts, _ = await _setup()
        sig_gen = SignalGenerator(strategy_id="STR-001", buy_threshold=0.10)

        # Apply
        result = await applier.apply(
            "STR-001",
            _make_optimization({"buy_threshold": 0.11}),
            _make_eval(),
            sig_gen,
        )
        assert sig_gen.buy_threshold == 0.11

        # Rollback
        success = await applier.rollback(result.tuning_id, sig_gen)
        assert success is True
        assert sig_gen.buy_threshold == 0.10

        # Verify status updated
        history = await ts.get_tuning_history(status=TuningStatus.ROLLED_BACK)
        assert len(history) >= 1

    async def test_rollback_nonexistent_id(self):
        applier, _, _ = await _setup()
        sig_gen = SignalGenerator(strategy_id="STR-001")
        success = await applier.rollback("nonexistent", sig_gen)
        assert success is False
