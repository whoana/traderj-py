"""Tests for engine.tuner.config."""

from engine.tuner.config import (
    ALL_BOUNDS,
    TIER_1_BOUNDS,
    TIER_2_BOUNDS,
    TIER_3_BOUNDS,
    GuardrailSettings,
    LLMProviderSettings,
    TunerScheduleSettings,
    TunerSettings,
    get_bounds_for_tier,
)
from engine.tuner.enums import TierLevel


def test_tuner_settings_defaults():
    s = TunerSettings()
    assert s.enabled is False
    assert s.llm.llm_primary == "claude"
    assert s.llm.monthly_budget_usd == 5.0
    assert s.schedule.tier1_eval_days == 7
    assert s.guardrails.max_change_pct == 0.20


def test_llm_provider_settings_defaults():
    s = LLMProviderSettings()
    assert s.claude_model == "claude-sonnet-4-20250514"
    assert s.openai_model == "gpt-4o"
    assert s.cb_failure_threshold == 3
    assert s.cb_recovery_timeout_min == 10


def test_schedule_settings():
    s = TunerScheduleSettings()
    assert s.tier1_cron_day == "mon"
    assert s.tier1_min_trades == 3
    assert s.tier2_interval_weeks == 2
    assert s.tier3_interval_weeks == 4


def test_guardrail_settings():
    s = GuardrailSettings()
    assert s.monitoring_hours == 48
    assert s.mdd_rollback_multiplier == 2.0
    assert s.optuna_n_trials == 50


def test_tier_1_bounds():
    names = {b.name for b in TIER_1_BOUNDS}
    assert "buy_threshold" in names
    assert "sell_threshold" in names
    assert "macro_weight" in names
    for b in TIER_1_BOUNDS:
        assert b.tier == TierLevel.TIER_1
        assert b.min_value < b.max_value


def test_tier_2_bounds():
    names = {b.name for b in TIER_2_BOUNDS}
    assert "atr_stop_multiplier" in names
    assert "max_position_pct" in names
    for b in TIER_2_BOUNDS:
        assert b.tier == TierLevel.TIER_2


def test_tier_3_bounds():
    names = {b.name for b in TIER_3_BOUNDS}
    assert "adx_trend_threshold" in names
    assert "debounce_count" in names
    for b in TIER_3_BOUNDS:
        assert b.tier == TierLevel.TIER_3


def test_all_bounds_dict():
    assert len(ALL_BOUNDS) == len(TIER_1_BOUNDS) + len(TIER_2_BOUNDS) + len(TIER_3_BOUNDS)
    assert "buy_threshold" in ALL_BOUNDS
    assert "atr_stop_multiplier" in ALL_BOUNDS
    assert "debounce_count" in ALL_BOUNDS


def test_get_bounds_for_tier():
    assert get_bounds_for_tier(TierLevel.TIER_1) is TIER_1_BOUNDS
    assert get_bounds_for_tier(TierLevel.TIER_2) is TIER_2_BOUNDS
    assert get_bounds_for_tier(TierLevel.TIER_3) is TIER_3_BOUNDS
