"""Tests for engine.tuner.enums."""

from engine.tuner.enums import (
    DiagnosisDirection,
    LLMConfidence,
    LLMProviderName,
    TierLevel,
    TunerState,
    TuningStatus,
)


def test_tier_level_values():
    assert TierLevel.TIER_1 == "tier_1"
    assert TierLevel.TIER_2 == "tier_2"
    assert TierLevel.TIER_3 == "tier_3"


def test_tuning_status_values():
    assert TuningStatus.PENDING == "pending"
    assert TuningStatus.MONITORING == "monitoring"
    assert TuningStatus.CONFIRMED == "confirmed"
    assert TuningStatus.ROLLED_BACK == "rolled_back"


def test_llm_provider_values():
    assert LLMProviderName.CLAUDE == "claude"
    assert LLMProviderName.OPENAI == "openai"
    assert LLMProviderName.DEGRADED == "degraded"


def test_confidence_values():
    assert LLMConfidence.HIGH == "high"
    assert LLMConfidence.LOW == "low"


def test_direction_values():
    assert DiagnosisDirection.INCREASE == "increase"
    assert DiagnosisDirection.DECREASE == "decrease"


def test_tuner_state_values():
    assert TunerState.IDLE == "idle"
    assert TunerState.SUSPENDED == "suspended"
