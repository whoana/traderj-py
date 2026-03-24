"""Tests for engine.tuner.degraded."""

import pytest

from engine.tuner.degraded import DegradedFallback
from engine.tuner.enums import DiagnosisDirection
from engine.tuner.models import EvalMetrics, OptimizerCandidate


def _make_metrics(**overrides) -> EvalMetrics:
    defaults = {
        "strategy_id": "STR-001",
        "eval_window": "2026-03-10~2026-03-17",
        "regime": "RANGING_LOW_VOL",
        "total_trades": 10,
        "win_rate": 0.50,
        "profit_factor": 1.2,
        "max_drawdown": 0.03,
        "avg_r_multiple": 1.0,
        "signal_accuracy": 0.40,
        "avg_holding_hours": 8.0,
        "total_return_pct": 0.02,
        "sharpe_ratio": 0.5,
    }
    defaults.update(overrides)
    return EvalMetrics(**defaults)


def _make_candidate(candidate_id: str, validation_pf: float, validation_mdd: float) -> OptimizerCandidate:
    return OptimizerCandidate(
        candidate_id=candidate_id,
        params={"buy_threshold": 0.12},
        validation_pf=validation_pf,
        validation_mdd=validation_mdd,
        validation_win_rate=0.5,
        validation_trades=10,
        optuna_trial_number=1,
    )


class TestDegradedDiagnose:
    def test_low_win_rate(self):
        fb = DegradedFallback()
        recs = fb.diagnose(_make_metrics(win_rate=0.20), {})
        names = [r.name for r in recs]
        assert "buy_threshold" in names
        assert any(r.direction == DiagnosisDirection.INCREASE for r in recs if r.name == "buy_threshold")

    def test_high_win_rate_low_pf(self):
        fb = DegradedFallback()
        recs = fb.diagnose(_make_metrics(win_rate=0.75, profit_factor=1.2), {})
        names = [r.name for r in recs]
        assert "reward_risk_ratio" in names

    def test_short_holding(self):
        fb = DegradedFallback()
        recs = fb.diagnose(_make_metrics(avg_holding_hours=1.5), {})
        names = [r.name for r in recs]
        assert "sell_threshold" in names

    def test_low_signal_accuracy(self):
        fb = DegradedFallback()
        recs = fb.diagnose(_make_metrics(signal_accuracy=0.10), {})
        names = [r.name for r in recs]
        assert "buy_threshold" in names

    def test_high_mdd(self):
        fb = DegradedFallback()
        recs = fb.diagnose(_make_metrics(max_drawdown=0.08), {})
        names = [r.name for r in recs]
        assert "max_position_pct" in names

    def test_low_r_multiple(self):
        fb = DegradedFallback()
        recs = fb.diagnose(_make_metrics(avg_r_multiple=0.3), {})
        names = [r.name for r in recs]
        assert "atr_stop_multiplier" in names

    def test_good_metrics_no_recommendations(self):
        fb = DegradedFallback()
        recs = fb.diagnose(_make_metrics(), {})
        assert len(recs) == 0


class TestDegradedSelect:
    def test_selects_highest_pf(self):
        fb = DegradedFallback()
        candidates = [
            _make_candidate("A", 1.2, 0.02),
            _make_candidate("B", 1.8, 0.03),
            _make_candidate("C", 1.5, 0.01),
        ]
        selected = fb.select_candidate(candidates)
        assert selected.candidate_id == "B"


class TestDegradedApprove:
    def test_approve_good_candidate(self):
        fb = DegradedFallback()
        c = _make_candidate("A", 1.5, 0.03)
        assert fb.approve(c, baseline_pf=1.0, baseline_mdd=0.04) is True

    def test_reject_low_pf(self):
        fb = DegradedFallback()
        c = _make_candidate("A", 0.8, 0.02)
        assert fb.approve(c, baseline_pf=1.0, baseline_mdd=0.04) is False

    def test_reject_high_mdd(self):
        fb = DegradedFallback()
        c = _make_candidate("A", 1.5, 0.08)
        assert fb.approve(c, baseline_pf=1.0, baseline_mdd=0.04) is False
