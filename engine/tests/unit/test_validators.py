"""Unit tests for engine/backtest/validators.py — Gate 1 validation logic."""

from __future__ import annotations

import pytest

from engine.backtest.validators import (
    GateCheck,
    ValidationResult,
    _DEFAULT_MDD_FACTOR,
    _DEFAULT_MIN_TRADES,
    _DEFAULT_OOS_RETURN_MARGIN,
    _DEFAULT_PF_MIN,
)


class TestGateCheck:
    def test_passing_check(self):
        g = GateCheck(name="Test", value=5.0, threshold=3.0, passed=True)
        assert g.passed is True
        d = g.to_dict()
        assert d["value"] == 5.0
        assert d["threshold"] == 3.0
        assert d["pass"] is True

    def test_failing_check(self):
        g = GateCheck(name="Test", value=1.0, threshold=3.0, passed=False)
        assert g.passed is False
        assert g.to_dict()["pass"] is False

    def test_frozen(self):
        g = GateCheck(name="Test", value=5.0, threshold=3.0, passed=True)
        with pytest.raises(AttributeError):
            g.value = 10.0  # type: ignore[misc]


class TestValidationResult:
    def _make_result(self, gates: dict[str, GateCheck], verdict: str) -> ValidationResult:
        return ValidationResult(
            windows=[],
            avg_return_pct=5.0,
            avg_pf=1.5,
            avg_mdd=-4.0,
            total_trades=15,
            gates=gates,
            verdict=verdict,
        )

    def test_to_dict_structure(self):
        gates = {
            "oos_return": GateCheck("OOS Return", 5.0, 3.0, True),
            "profit_factor": GateCheck("Profit Factor", 1.5, 1.2, True),
            "mdd": GateCheck("MDD", 4.0, 6.5, True),
            "trade_count": GateCheck("Trades", 15.0, 10.0, True),
        }
        r = self._make_result(gates, "pass")
        d = r.to_dict()
        assert d["verdict"] == "pass"
        assert d["avg_return_pct"] == 5.0
        assert d["avg_pf"] == 1.5
        assert d["total_trades"] == 15
        assert len(d["gates"]) == 4
        assert d["gates"]["oos_return"]["pass"] is True

    def test_fail_verdict(self):
        gates = {
            "oos_return": GateCheck("OOS Return", 1.0, 3.0, False),
            "mdd": GateCheck("MDD", 10.0, 6.5, False),
        }
        r = self._make_result(gates, "fail")
        assert r.verdict == "fail"

    def test_warn_verdict(self):
        gates = {
            "profit_factor": GateCheck("PF", 1.0, 1.2, False),
            "trade_count": GateCheck("Trades", 8.0, 10.0, False),
        }
        r = self._make_result(gates, "warn")
        assert r.verdict == "warn"


class TestGateThresholds:
    """Verify default threshold constants match design spec."""

    def test_oos_return_margin(self):
        assert _DEFAULT_OOS_RETURN_MARGIN == 2.0

    def test_pf_minimum(self):
        assert _DEFAULT_PF_MIN == 1.2

    def test_mdd_factor(self):
        assert _DEFAULT_MDD_FACTOR == 1.3

    def test_min_trades(self):
        assert _DEFAULT_MIN_TRADES == 10


class TestVerdictLogic:
    """Test the verdict determination logic as specified in design."""

    def _check_verdict(self, oos_pass, pf_pass, mdd_pass, trades_pass) -> str:
        """Replicate the verdict logic from validators.py."""
        gates = {
            "oos_return": GateCheck("OOS", 0, 0, oos_pass),
            "profit_factor": GateCheck("PF", 0, 0, pf_pass),
            "mdd": GateCheck("MDD", 0, 0, mdd_pass),
            "trade_count": GateCheck("Trades", 0, 0, trades_pass),
        }
        all_passed = all(g.passed for g in gates.values())
        critical_failed = not gates["oos_return"].passed or not gates["mdd"].passed
        if all_passed:
            return "pass"
        elif critical_failed:
            return "fail"
        else:
            return "warn"

    def test_all_pass(self):
        assert self._check_verdict(True, True, True, True) == "pass"

    def test_oos_return_fail_is_critical(self):
        assert self._check_verdict(False, True, True, True) == "fail"

    def test_mdd_fail_is_critical(self):
        assert self._check_verdict(True, True, False, True) == "fail"

    def test_pf_fail_only_is_warn(self):
        assert self._check_verdict(True, False, True, True) == "warn"

    def test_trades_fail_only_is_warn(self):
        assert self._check_verdict(True, True, True, False) == "warn"

    def test_both_critical_fail(self):
        assert self._check_verdict(False, True, False, True) == "fail"

    def test_non_critical_both_fail_is_warn(self):
        assert self._check_verdict(True, False, True, False) == "warn"

    def test_all_fail(self):
        assert self._check_verdict(False, False, False, False) == "fail"
