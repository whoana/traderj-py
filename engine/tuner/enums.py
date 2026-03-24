"""AI Tuner enumerations."""

from __future__ import annotations

from enum import StrEnum


class TierLevel(StrEnum):
    """Parameter tuning frequency tier."""

    TIER_1 = "tier_1"  # Signal params (weekly)
    TIER_2 = "tier_2"  # Risk params (bi-weekly)
    TIER_3 = "tier_3"  # Regime params (monthly)


class TuningStatus(StrEnum):
    """Tuning session lifecycle status."""

    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    MONITORING = "monitoring"
    CONFIRMED = "confirmed"


class LLMProviderName(StrEnum):
    """LLM provider identifier."""

    CLAUDE = "claude"
    OPENAI = "openai"
    DEGRADED = "degraded"


class LLMConfidence(StrEnum):
    """LLM self-assessed diagnosis confidence."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DiagnosisDirection(StrEnum):
    """Parameter adjustment direction."""

    INCREASE = "increase"
    DECREASE = "decrease"


class TunerState(StrEnum):
    """Tuner pipeline overall state."""

    IDLE = "idle"
    EVALUATING = "evaluating"
    OPTIMIZING = "optimizing"
    APPLYING = "applying"
    MONITORING = "monitoring"
    SUSPENDED = "suspended"
