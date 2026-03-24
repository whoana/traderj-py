"""AI Tuner data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from engine.tuner.enums import (
    DiagnosisDirection,
    LLMConfidence,
    LLMProviderName,
    TierLevel,
    TuningStatus,
)


@dataclass(frozen=True)
class ParameterBounds:
    """Valid range for a tunable parameter."""

    name: str
    tier: TierLevel
    min_value: float
    max_value: float
    max_change_pct: float = 0.20


@dataclass(frozen=True)
class EvalMetrics:
    """Quantitative strategy performance metrics."""

    strategy_id: str
    eval_window: str
    regime: str | None
    total_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    avg_r_multiple: float
    signal_accuracy: float
    avg_holding_hours: float
    total_return_pct: float
    sharpe_ratio: float


@dataclass(frozen=True)
class ParamRecommendation:
    """Single parameter adjustment recommendation."""

    name: str
    direction: DiagnosisDirection
    reason: str


@dataclass(frozen=True)
class LLMResponse:
    """LLM API call response."""

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    provider: str
    model: str


@dataclass(frozen=True)
class LLMDiagnosis:
    """LLM diagnosis result."""

    root_causes: list[str]
    recommended_params: list[ParamRecommendation]
    confidence: LLMConfidence
    raw_response: str
    provider: LLMProviderName
    model: str
    tokens_used: int
    cost_usd: float


@dataclass(frozen=True)
class OptimizerCandidate:
    """Parameter candidate from Optuna optimization."""

    candidate_id: str
    params: dict[str, float]
    validation_pf: float
    validation_mdd: float
    validation_win_rate: float
    validation_trades: int
    optuna_trial_number: int


@dataclass(frozen=True)
class TuningDecision:
    """Final parameter application decision."""

    approved: bool
    selected_candidate: OptimizerCandidate | None
    reason: str
    provider: LLMProviderName
    model: str | None


@dataclass(frozen=True)
class ParameterChange:
    """Single parameter value change record."""

    parameter_name: str
    tier: TierLevel
    old_value: float
    new_value: float
    change_pct: float


@dataclass(frozen=True)
class TuningHistoryRecord:
    """Tuning session history record (maps to tuning_history rows)."""

    tuning_id: str
    created_at: datetime
    strategy_id: str
    changes: list[ParameterChange]
    eval_metrics: EvalMetrics
    validation_pf: float | None
    validation_mdd: float | None
    llm_provider: LLMProviderName
    llm_model: str | None
    llm_diagnosis: str | None
    llm_confidence: LLMConfidence | None
    reason: str
    status: TuningStatus


@dataclass(frozen=True)
class TuningReport:
    """Tuning evaluation report (maps to tuning_report row)."""

    tuning_id: str
    created_at: datetime
    eval_window: str
    strategy_id: str
    metrics: EvalMetrics
    recommendations: list[ParamRecommendation]
    applied_changes: list[ParameterChange]
    status: TuningStatus


@dataclass
class EvaluationResult:
    """StrategyEvaluator output."""

    metrics: EvalMetrics
    diagnosis: LLMDiagnosis | None
    rule_diagnosis: list[ParamRecommendation]
    should_tune: bool
    skip_reason: str | None


@dataclass
class OptimizationResult:
    """HybridOptimizer output."""

    candidates: list[OptimizerCandidate]
    selected: OptimizerCandidate | None
    decision: TuningDecision
    optuna_study_stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApplyResult:
    """ParameterApplier output."""

    tuning_id: str
    changes: list[ParameterChange]
    status: TuningStatus
    monitoring_until: datetime | None


@dataclass
class GuardrailResult:
    """Guardrails validation output."""

    passed: bool
    violations: list[str]
    clamped_changes: list[ParameterChange]
    requires_approval: bool


@dataclass
class RollbackCheckResult:
    """RollbackMonitor check output."""

    action: str  # "continue" | "rollback" | "confirm" | "suspend"
    reason: str


@dataclass
class TuningSessionResult:
    """Full tuning session output."""

    tuning_id: str
    strategy_id: str
    tier: TierLevel
    status: TuningStatus
    changes: list[ParameterChange]
    eval_metrics: EvalMetrics | None
    reason: str
