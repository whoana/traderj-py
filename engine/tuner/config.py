"""AI Tuner configuration and parameter bounds registry."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from engine.tuner.enums import TierLevel
from engine.tuner.models import ParameterBounds


class LLMProviderSettings(BaseSettings):
    model_config = {"env_prefix": "TUNER_", "extra": "ignore"}

    llm_primary: str = "claude"
    llm_fallback: str = "openai"
    llm_degraded_enabled: bool = True

    claude_model: str = "claude-sonnet-4-20250514"
    claude_timeout: int = 30

    openai_model: str = "gpt-4o"
    openai_timeout: int = 30

    monthly_budget_usd: float = 5.0
    budget_warning_pct: float = 0.8

    cb_failure_threshold: int = 3
    cb_recovery_timeout_min: int = 10


class TunerScheduleSettings(BaseSettings):
    model_config = {"env_prefix": "TUNER_", "extra": "ignore"}

    tier1_cron_day: str = "mon"
    tier1_cron_hour: int = 0
    tier1_eval_days: int = 7
    tier1_min_trades: int = 3

    tier2_interval_weeks: int = 2
    tier2_eval_days: int = 14
    tier2_min_trades: int = 5

    tier3_interval_weeks: int = 4
    tier3_eval_days: int = 30
    tier3_min_trades: int = 10


class GuardrailSettings(BaseSettings):
    model_config = {"env_prefix": "TUNER_", "extra": "ignore"}

    max_change_pct: float = 0.20
    monitoring_hours: int = 48
    mdd_rollback_multiplier: float = 2.0
    max_consecutive_rollbacks: int = 3
    consecutive_loss_rollback: int = 5

    optuna_n_trials: int = 50
    optuna_top_k: int = 3

    wf_train_bars: int = 1440
    wf_test_bars: int = 720


class TunerSettings(BaseSettings):
    """Root tuner settings, integrated into AppSettings."""

    model_config = {"env_prefix": "TUNER_", "env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    enabled: bool = False
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    schedule: TunerScheduleSettings = Field(default_factory=TunerScheduleSettings)
    guardrails: GuardrailSettings = Field(default_factory=GuardrailSettings)


# ── Parameter Bounds Registry ──

TIER_1_BOUNDS: list[ParameterBounds] = [
    ParameterBounds("buy_threshold", TierLevel.TIER_1, 0.03, 0.25),
    ParameterBounds("sell_threshold", TierLevel.TIER_1, -0.20, -0.02),
    ParameterBounds("tf_weight_1h", TierLevel.TIER_1, 0.1, 0.8),
    ParameterBounds("tf_weight_4h", TierLevel.TIER_1, 0.1, 0.8),
    ParameterBounds("tf_weight_1d", TierLevel.TIER_1, 0.0, 0.8),
    ParameterBounds("macro_weight", TierLevel.TIER_1, 0.0, 0.30),
    ParameterBounds("score_w1", TierLevel.TIER_1, 0.10, 0.60),
    ParameterBounds("score_w2", TierLevel.TIER_1, 0.10, 0.60),
    ParameterBounds("score_w3", TierLevel.TIER_1, 0.10, 0.60),
]

TIER_2_BOUNDS: list[ParameterBounds] = [
    ParameterBounds("atr_stop_multiplier", TierLevel.TIER_2, 1.5, 3.0),
    ParameterBounds("reward_risk_ratio", TierLevel.TIER_2, 1.5, 4.0),
    ParameterBounds("trailing_stop_activation_pct", TierLevel.TIER_2, 0.005, 0.03),
    ParameterBounds("trailing_stop_distance_pct", TierLevel.TIER_2, 0.008, 0.03),
    ParameterBounds("max_position_pct", TierLevel.TIER_2, 0.05, 0.30),
    ParameterBounds("volatility_cap_pct", TierLevel.TIER_2, 0.05, 0.12),
    ParameterBounds("daily_max_loss_pct", TierLevel.TIER_2, 0.03, 0.08),
]

TIER_3_BOUNDS: list[ParameterBounds] = [
    ParameterBounds("adx_trend_threshold", TierLevel.TIER_3, 20.0, 35.0),
    ParameterBounds("bb_width_vol_threshold", TierLevel.TIER_3, 0.02, 0.08),
    ParameterBounds("debounce_count", TierLevel.TIER_3, 2.0, 5.0),
    ParameterBounds("cooldown_minutes", TierLevel.TIER_3, 30.0, 120.0),
]

ALL_BOUNDS: dict[str, ParameterBounds] = {b.name: b for b in TIER_1_BOUNDS + TIER_2_BOUNDS + TIER_3_BOUNDS}


def get_bounds_for_tier(tier: TierLevel) -> list[ParameterBounds]:
    """Return all parameter bounds for a given tier."""
    if tier == TierLevel.TIER_1:
        return TIER_1_BOUNDS
    if tier == TierLevel.TIER_2:
        return TIER_2_BOUNDS
    return TIER_3_BOUNDS
