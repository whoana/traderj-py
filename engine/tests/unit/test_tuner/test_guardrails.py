"""Tests for engine.tuner.guardrails."""

from __future__ import annotations

from engine.data.sqlite_store import SqliteDataStore
from engine.tuner.config import GuardrailSettings
from engine.tuner.enums import DiagnosisDirection, TierLevel, TuningStatus
from engine.tuner.guardrails import Guardrails
from engine.tuner.models import ParameterBounds, ParameterChange
from engine.tuner.store import TunerStore

from ..test_tuner.test_store import _make_record


async def _setup() -> tuple[Guardrails, TunerStore]:
    ds = SqliteDataStore(":memory:")
    await ds.connect()
    ts = TunerStore(ds)
    config = GuardrailSettings()
    return Guardrails(config, ts), ts


class TestClampChange:
    def test_within_bounds(self):
        g = Guardrails.__new__(Guardrails)
        bounds = ParameterBounds("buy_threshold", TierLevel.TIER_1, 0.03, 0.25)
        result = g.clamp_change("buy_threshold", 0.10, 0.11, bounds)
        assert result == 0.11  # within ±20% of 0.10

    def test_exceeds_max_change_pct(self):
        g = Guardrails.__new__(Guardrails)
        bounds = ParameterBounds("buy_threshold", TierLevel.TIER_1, 0.03, 0.25, max_change_pct=0.20)
        # 0.10 + 20% = 0.12 max
        result = g.clamp_change("buy_threshold", 0.10, 0.15, bounds)
        assert result == 0.12

    def test_below_min_value(self):
        g = Guardrails.__new__(Guardrails)
        bounds = ParameterBounds("buy_threshold", TierLevel.TIER_1, 0.03, 0.25)
        result = g.clamp_change("buy_threshold", 0.05, 0.01, bounds)
        assert result == 0.04  # max(0.03, 0.05 - 0.01) = 0.04

    def test_above_max_value(self):
        g = Guardrails.__new__(Guardrails)
        bounds = ParameterBounds("buy_threshold", TierLevel.TIER_1, 0.03, 0.25)
        result = g.clamp_change("buy_threshold", 0.24, 0.30, bounds)
        assert result == 0.25  # clamped to max_value

    def test_zero_old_value(self):
        g = Guardrails.__new__(Guardrails)
        bounds = ParameterBounds("macro_weight", TierLevel.TIER_1, 0.0, 0.30, max_change_pct=0.20)
        result = g.clamp_change("macro_weight", 0.0, 0.10, bounds)
        # delta = (0.30 - 0.0) * 0.20 = 0.06
        assert result <= 0.06
        assert result >= 0.0


class TestNormalizeWeights:
    def test_normalize_tf_weights(self):
        changes = [
            ParameterChange("tf_weight_1h", TierLevel.TIER_1, 0.3, 0.4, 0.33),
            ParameterChange("tf_weight_4h", TierLevel.TIER_1, 0.5, 0.6, 0.20),
            ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20),
        ]
        result = Guardrails.normalize_weights(changes, "tf_weight_")
        tf_sum = sum(c.new_value for c in result if c.parameter_name.startswith("tf_weight_"))
        assert abs(tf_sum - 1.0) < 1e-6
        # Non-tf_weight should be unchanged
        assert result[2].new_value == 0.12

    def test_no_matching_prefix(self):
        changes = [
            ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20),
        ]
        result = Guardrails.normalize_weights(changes, "tf_weight_")
        assert result == changes

    def test_already_normalized(self):
        changes = [
            ParameterChange("score_w1", TierLevel.TIER_1, 0.4, 0.5, 0.25),
            ParameterChange("score_w2", TierLevel.TIER_1, 0.3, 0.3, 0.0),
            ParameterChange("score_w3", TierLevel.TIER_1, 0.3, 0.2, -0.33),
        ]
        result = Guardrails.normalize_weights(changes, "score_w")
        # Sum = 1.0, should be unchanged
        assert result[0].new_value == 0.5
        assert result[1].new_value == 0.3
        assert result[2].new_value == 0.2


class TestCheckTier2Direction:
    async def test_no_history_allows(self):
        g, ts = await _setup()
        allowed = await g.check_tier2_direction("STR-001", "atr_stop_multiplier", DiagnosisDirection.INCREASE)
        assert allowed is True

    async def test_same_direction_blocked(self):
        g, ts = await _setup()
        # Save a record with buy_threshold increasing (0.10 -> 0.12)
        await ts.save_tuning_history(_make_record())
        allowed = await g.check_tier2_direction("STR-001", "buy_threshold", DiagnosisDirection.INCREASE)
        assert allowed is False

    async def test_different_direction_allowed(self):
        g, ts = await _setup()
        await ts.save_tuning_history(_make_record())
        allowed = await g.check_tier2_direction("STR-001", "buy_threshold", DiagnosisDirection.DECREASE)
        assert allowed is True


class TestValidateChanges:
    async def test_valid_tier1_changes(self):
        g, _ = await _setup()
        changes = [
            ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.11, 0.10),
            ParameterChange("sell_threshold", TierLevel.TIER_1, -0.10, -0.09, 0.10),
        ]
        result = await g.validate_changes(changes, "STR-001")
        assert result.passed is True
        assert result.requires_approval is False
        assert len(result.clamped_changes) == 2

    async def test_tier3_requires_approval(self):
        g, _ = await _setup()
        changes = [
            ParameterChange("adx_trend_threshold", TierLevel.TIER_3, 25.0, 27.0, 0.08),
        ]
        result = await g.validate_changes(changes, "STR-001")
        assert result.requires_approval is True

    async def test_unknown_parameter_violation(self):
        g, _ = await _setup()
        changes = [
            ParameterChange("nonexistent_param", TierLevel.TIER_1, 0.1, 0.2, 1.0),
        ]
        result = await g.validate_changes(changes, "STR-001")
        assert any("Unknown parameter" in v for v in result.violations)

    async def test_clamping_applied(self):
        g, _ = await _setup()
        changes = [
            ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.50, 4.0),
        ]
        result = await g.validate_changes(changes, "STR-001")
        # Should be clamped from 0.50 down to at most 0.12 (0.10 + 20%)
        clamped = result.clamped_changes[0]
        assert clamped.new_value <= 0.12
        assert any("clamped" in v for v in result.violations)
