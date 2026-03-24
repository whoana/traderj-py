"""Tests for engine.tuner.optimizer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.strategy.risk import RiskConfig
from engine.strategy.signal import SignalGenerator
from engine.tuner.config import GuardrailSettings
from engine.tuner.degraded import DegradedFallback
from engine.tuner.enums import LLMProviderName, TierLevel
from engine.tuner.models import (
    EvalMetrics,
    EvaluationResult,
    LLMResponse,
    OptimizerCandidate,
    TuningDecision,
)
from engine.tuner.optimizer import HybridOptimizer
from engine.tuner.provider_router import ProviderRouter


def _make_optimizer(router: ProviderRouter | None = None) -> HybridOptimizer:
    if router is None:
        router = MagicMock(spec=ProviderRouter)
        router.complete = AsyncMock(return_value=None)
    degraded = DegradedFallback()
    config = GuardrailSettings(optuna_n_trials=5, optuna_top_k=2)
    return HybridOptimizer(router, degraded, config)


def _make_candidate(cid: str, pf: float, mdd: float) -> OptimizerCandidate:
    return OptimizerCandidate(
        candidate_id=cid,
        params={"buy_threshold": 0.12},
        validation_pf=pf,
        validation_mdd=mdd,
        validation_win_rate=0.5,
        validation_trades=10,
        optuna_trial_number=1,
    )


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


class TestNarrowBounds:
    def test_basic_narrowing(self):
        from engine.tuner.models import ParameterBounds

        opt = _make_optimizer()
        bounds = ParameterBounds("buy_threshold", TierLevel.TIER_1, 0.03, 0.25)
        low, high = opt._narrow_bounds(0.10, bounds, 0.20)
        assert low == pytest.approx(0.08, abs=0.001)
        assert high == pytest.approx(0.12, abs=0.001)

    def test_narrow_at_boundary(self):
        from engine.tuner.models import ParameterBounds

        opt = _make_optimizer()
        bounds = ParameterBounds("buy_threshold", TierLevel.TIER_1, 0.03, 0.25)
        low, high = opt._narrow_bounds(0.04, bounds, 0.20)
        # 0.04 - 0.008 = 0.032 but min is 0.03
        assert low >= 0.03
        assert high <= 0.25

    def test_zero_value_uses_range(self):
        from engine.tuner.models import ParameterBounds

        opt = _make_optimizer()
        bounds = ParameterBounds("macro_weight", TierLevel.TIER_1, 0.0, 0.30)
        low, high = opt._narrow_bounds(0.0, bounds, 0.20)
        assert low >= 0.0
        assert high > 0.0  # Should use range-based delta


class TestBuildSignalGenerator:
    def test_applies_tier1_params(self):
        base = SignalGenerator(strategy_id="STR-001", buy_threshold=0.10, sell_threshold=-0.10)
        params = {"buy_threshold": 0.12, "sell_threshold": -0.08, "macro_weight": 0.15}
        result = HybridOptimizer._build_signal_generator(base, params)
        assert result.buy_threshold == 0.12
        assert result.sell_threshold == -0.08
        assert result.macro_weight == 0.15

    def test_applies_tf_weights(self):
        base = SignalGenerator(strategy_id="STR-001", tf_weights={"1h": 0.3, "4h": 0.5})
        params = {"tf_weight_1h": 0.4, "tf_weight_4h": 0.6}
        result = HybridOptimizer._build_signal_generator(base, params)
        assert result.tf_weights["1h"] == 0.4
        assert result.tf_weights["4h"] == 0.6

    def test_preserves_unmodified_params(self):
        base = SignalGenerator(strategy_id="STR-001", buy_threshold=0.10, sell_threshold=-0.10)
        params = {"buy_threshold": 0.12}
        result = HybridOptimizer._build_signal_generator(base, params)
        assert result.sell_threshold == -0.10  # unchanged
        assert result.strategy_id == "STR-001"


class TestBuildRiskConfig:
    def test_applies_tier2_params(self):
        base = RiskConfig(atr_stop_multiplier=2.0, reward_risk_ratio=2.0)
        params = {"atr_stop_multiplier": 2.5, "reward_risk_ratio": 3.0}
        result = HybridOptimizer._build_risk_config(base, params)
        assert result.atr_stop_multiplier == 2.5
        assert result.reward_risk_ratio == 3.0

    def test_ignores_non_tier2_params(self):
        base = RiskConfig()
        params = {"buy_threshold": 0.12, "atr_stop_multiplier": 2.5}
        result = HybridOptimizer._build_risk_config(base, params)
        assert result.atr_stop_multiplier == 2.5
        assert not hasattr(result, "buy_threshold") or result.max_position_pct == 0.20

    def test_none_base_uses_defaults(self):
        params = {"max_position_pct": 0.15}
        result = HybridOptimizer._build_risk_config(None, params)
        assert result.max_position_pct == 0.15
        assert result.atr_stop_multiplier == 2.0  # default


class TestSelectCandidate:
    async def test_degraded_fallback_selects_highest_pf(self):
        opt = _make_optimizer()
        candidates = [
            _make_candidate("C-001", 1.2, 0.02),
            _make_candidate("C-002", 1.8, 0.03),
            _make_candidate("C-003", 1.5, 0.01),
        ]
        selected = await opt._select_candidate("STR-001", candidates, _make_eval())
        assert selected.candidate_id == "C-002"

    async def test_llm_selection(self):
        router = MagicMock(spec=ProviderRouter)
        router.complete = AsyncMock(return_value=LLMResponse(
            text='{"selected_candidate_id": "C-001", "reasoning": "safe", "risk_assessment": "low", "confidence": "high"}',
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            provider="claude",
            model="claude-sonnet",
        ))
        opt = _make_optimizer(router)
        candidates = [
            _make_candidate("C-001", 1.2, 0.01),
            _make_candidate("C-002", 1.8, 0.03),
        ]
        selected = await opt._select_candidate("STR-001", candidates, _make_eval())
        assert selected.candidate_id == "C-001"


class TestApproveCandidate:
    async def test_degraded_approval(self):
        opt = _make_optimizer()
        candidate = _make_candidate("C-001", 1.5, 0.02)
        decision = await opt._approve_candidate(
            "STR-001", candidate,
            {"pf": 1.5, "mdd": 0.02, "trades": 10, "win_rate": 0.5},
            baseline_pf=1.0, baseline_mdd=0.03,
            baseline_wr=0.4, baseline_trades=8,
        )
        assert decision.approved is True
        assert decision.provider == LLMProviderName.DEGRADED

    async def test_degraded_rejection_low_pf(self):
        opt = _make_optimizer()
        candidate = _make_candidate("C-001", 0.8, 0.02)
        decision = await opt._approve_candidate(
            "STR-001", candidate,
            {"pf": 0.8, "mdd": 0.02, "trades": 10, "win_rate": 0.5},
            baseline_pf=1.0, baseline_mdd=0.03,
            baseline_wr=0.4, baseline_trades=8,
        )
        assert decision.approved is False


class TestStudyStats:
    def test_stats_from_study(self):
        import optuna

        study = optuna.create_study(direction="maximize")
        study.optimize(lambda t: t.suggest_float("x", 0, 1), n_trials=3)
        stats = HybridOptimizer._study_stats(study)
        assert stats["n_trials"] == 3
        assert stats["n_completed"] == 3
        assert stats["best_value"] is not None
