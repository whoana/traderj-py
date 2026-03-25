# AI Tuner 모듈 상세설계서

> **기획서:** `docs/전략개선.md`
> **작성일:** 2026-03-24
> **대상:** `engine/tuner/` 패키지

---

## 1. 모듈 구조

```
engine/tuner/
    __init__.py              # Public API: create_tuner()
    enums.py                 # TierLevel, TuningStatus, LLMProviderName 등
    models.py                # Pydantic/dataclass 모델 정의
    config.py                # TunerSettings + 파라미터 범위 레지스트리
    store.py                 # TunerStore: tuning_history / tuning_report DB 접근
    llm_client.py            # LLMClient Protocol + Claude/OpenAI 구현체
    provider_router.py       # ProviderRouter + CircuitBreaker + CostTracker
    prompts.py               # LLM 프롬프트 템플릿 4종
    degraded.py              # DegradedFallback: LLM 장애 시 규칙 기반 대체
    evaluator.py             # StrategyEvaluator: 성과 평가 + LLM 진단
    optimizer.py             # HybridOptimizer: Optuna + LLM 후보 선택
    guardrails.py            # Guardrails: 변경 폭 제한, Tier 규칙
    applier.py               # ParameterApplier: hot-reload + 이력 저장
    rollback.py              # RollbackMonitor: 48h 모니터링 + 자동 롤백
    pipeline.py              # TunerPipeline: Evaluator → Optimizer → Applier 오케스트레이션
```

### 모듈별 책임

| 모듈 | 책임 | 의존 |
|------|------|------|
| `enums.py` | 열거형 정의 | 없음 |
| `models.py` | 데이터 구조 정의 | `enums` |
| `config.py` | 환경변수 기반 설정 + 파라미터 범위 | `enums`, `models` |
| `store.py` | DB CRUD (tuning 테이블) | `models`, DataStore |
| `llm_client.py` | LLM API 호출 추상화 | `httpx` |
| `provider_router.py` | LLM 프로바이더 선택 + 장애 관리 | `llm_client` |
| `prompts.py` | 프롬프트 템플릿 관리 | `models` |
| `degraded.py` | 규칙 기반 진단/선택/승인 | `models` |
| `evaluator.py` | 성과 지표 계산 + LLM 진단 | `store`, `provider_router`, `degraded`, DataStore |
| `optimizer.py` | Optuna 탐색 + LLM 후보 선택 | `provider_router`, `degraded`, `guardrails`, BacktestEngine |
| `guardrails.py` | 안전 규칙 검증 + 값 클램핑 | `config`, `store` |
| `applier.py` | 파라미터 반영 + 이력 저장 | `store`, `guardrails`, SignalGenerator |
| `rollback.py` | 모니터링 + 자동 롤백 | `store`, `applier`, DataStore |
| `pipeline.py` | 전체 파이프라인 오케스트레이션 | 전체 모듈 |

---

## 2. 클래스 다이어그램

```
                         ┌─────────────────────┐
                         │   AppOrchestrator    │
                         │   (engine/app.py)    │
                         └──────────┬──────────┘
                                    │ registers "tuner_pipeline"
                                    ▼
                         ┌─────────────────────┐
                         │   TunerPipeline      │
                         │   (pipeline.py)      │
                         └──┬─────┬─────┬──────┘
                            │     │     │
               ┌────────────┘     │     └────────────┐
               ▼                  ▼                   ▼
    ┌──────────────────┐ ┌───────────────────┐ ┌──────────────────┐
    │ StrategyEvaluator│ │ HybridOptimizer   │ │ ParameterApplier │
    │ (evaluator.py)   │ │ (optimizer.py)    │ │ (applier.py)     │
    └────────┬─────────┘ └───────┬───────────┘ └───────┬──────────┘
             │                   │                     │
             │                   │                     ├→ SignalGenerator
             │                   │                     ├→ RiskEngine
             │                   │                     ├→ RegimeSwitchManager
             │                   │                     └→ TunerStore
             │                   │
             │                   ├→ BacktestEngine (기존)
             │                   ├→ WalkForwardEngine (기존)
             │                   └→ Optuna (study.optimize)
             │
             ├→ DataStore (기존)
             └→ compute_metrics() (기존)

    모든 모듈이 공유:
    ┌─────────────────────┐         ┌─────────────────┐
    │   ProviderRouter    │────────→│   LLMClient     │ (Protocol)
    │  (provider_router)  │         └─────────────────┘
    └─────────┬───────────┘            ▲          ▲
              │                 ┌──────┘          └──────┐
              │       ┌────────────────┐    ┌─────────────────┐
              │       │ ClaudeLLMClient│    │ OpenAILLMClient │
              │       └────────────────┘    └─────────────────┘
              │
              ├→ LLMCircuitBreaker (프로바이더별)
              ├→ CostTracker (월간 예산)
              └→ DegradedFallback (degraded.py)

    ┌─────────────────┐       ┌──────────────────┐
    │   Guardrails    │       │ RollbackMonitor  │
    │ (guardrails.py) │       │ (rollback.py)    │
    └─────────────────┘       └──────────────────┘
```

---

## 3. Enum 정의

**파일:** `engine/tuner/enums.py`

```python
from enum import StrEnum


class TierLevel(StrEnum):
    """파라미터 조정 빈도 계층."""
    TIER_1 = "tier_1"   # 시그널 파라미터 (주 1회)
    TIER_2 = "tier_2"   # 리스크 파라미터 (2~4주)
    TIER_3 = "tier_3"   # 레짐 파라미터 (월 1회)


class TuningStatus(StrEnum):
    """튜닝 세션 상태."""
    PENDING = "pending"           # 승인 대기 (Tier 3)
    APPLIED = "applied"           # 반영 완료
    REJECTED = "rejected"         # 거부됨
    ROLLED_BACK = "rolled_back"   # 롤백됨
    MONITORING = "monitoring"     # 48시간 모니터링 중
    CONFIRMED = "confirmed"       # 모니터링 통과, 확정


class LLMProviderName(StrEnum):
    """LLM 프로바이더 식별자."""
    CLAUDE = "claude"
    OPENAI = "openai"
    DEGRADED = "degraded"         # 규칙 기반 모드


class LLMConfidence(StrEnum):
    """LLM 자체 진단 신뢰도."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DiagnosisDirection(StrEnum):
    """파라미터 조정 방향."""
    INCREASE = "increase"
    DECREASE = "decrease"


class TunerState(StrEnum):
    """튜너 파이프라인 전체 상태."""
    IDLE = "idle"
    EVALUATING = "evaluating"
    OPTIMIZING = "optimizing"
    APPLYING = "applying"
    MONITORING = "monitoring"
    SUSPENDED = "suspended"       # 3회 연속 롤백 시
```

---

## 4. 데이터 모델

**파일:** `engine/tuner/models.py`

```python
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
    """튜닝 가능한 파라미터의 유효 범위 정의."""
    name: str
    tier: TierLevel
    min_value: float
    max_value: float
    max_change_pct: float = 0.20  # 1회 최대 변경 비율


@dataclass(frozen=True)
class EvalMetrics:
    """전략 성과 정량 지표."""
    strategy_id: str
    eval_window: str                # "2026-03-10~2026-03-17"
    regime: str | None
    total_trades: int
    win_rate: float                 # 0.0~1.0
    profit_factor: float
    max_drawdown: float             # 0.0~1.0
    avg_r_multiple: float
    signal_accuracy: float          # 0.0~1.0
    avg_holding_hours: float
    total_return_pct: float
    sharpe_ratio: float


@dataclass(frozen=True)
class ParamRecommendation:
    """단일 파라미터 조정 권고."""
    name: str
    direction: DiagnosisDirection
    reason: str


@dataclass(frozen=True)
class LLMDiagnosis:
    """LLM 진단 결과."""
    root_causes: list[str]
    recommended_params: list[ParamRecommendation]
    confidence: LLMConfidence
    raw_response: str               # LLM 원본 JSON 응답
    provider: LLMProviderName
    model: str
    tokens_used: int
    cost_usd: float


@dataclass(frozen=True)
class OptimizerCandidate:
    """Optuna가 생성한 파라미터 후보."""
    candidate_id: str
    params: dict[str, float]        # {param_name: new_value}
    validation_pf: float
    validation_mdd: float
    validation_win_rate: float
    validation_trades: int
    optuna_trial_number: int


@dataclass(frozen=True)
class TuningDecision:
    """최종 파라미터 적용 판단."""
    approved: bool
    selected_candidate: OptimizerCandidate | None
    reason: str                     # LLM 또는 규칙 기반 근거
    provider: LLMProviderName
    model: str | None


@dataclass(frozen=True)
class ParameterChange:
    """단일 파라미터 변경 기록."""
    parameter_name: str
    tier: TierLevel
    old_value: float
    new_value: float
    change_pct: float               # 부호 포함 변경 비율


@dataclass(frozen=True)
class TuningHistoryRecord:
    """튜닝 세션 이력 레코드 (tuning_history 테이블 매핑)."""
    tuning_id: str
    created_at: datetime
    strategy_id: str
    changes: list[ParameterChange]
    eval_metrics: EvalMetrics
    validation_pf: float | None
    validation_mdd: float | None
    llm_provider: LLMProviderName
    llm_model: str | None
    llm_diagnosis: str | None       # JSON 문자열
    llm_confidence: LLMConfidence | None
    reason: str
    status: TuningStatus


@dataclass(frozen=True)
class TuningReport:
    """튜닝 보고서 (tuning_report 테이블 매핑)."""
    tuning_id: str
    created_at: datetime
    eval_window: str
    strategy_id: str
    metrics: EvalMetrics
    recommendations: list[ParamRecommendation]
    applied_changes: list[ParameterChange]
    status: TuningStatus


@dataclass(frozen=True)
class LLMResponse:
    """LLM API 호출 응답."""
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    provider: str
    model: str


@dataclass
class EvaluationResult:
    """Evaluator 출력 결과."""
    metrics: EvalMetrics
    diagnosis: LLMDiagnosis | None            # Degraded 모드에서는 None
    rule_diagnosis: list[ParamRecommendation]  # 항상 계산 (감사 추적용)
    should_tune: bool                          # False면 성과 양호 → 스킵
    skip_reason: str | None                    # "insufficient_trades", "metrics_acceptable" 등


@dataclass
class OptimizationResult:
    """Optimizer 출력 결과."""
    candidates: list[OptimizerCandidate]
    selected: OptimizerCandidate | None
    decision: TuningDecision
    optuna_study_stats: dict[str, Any]         # n_trials, best_value, duration_sec


@dataclass
class ApplyResult:
    """Applier 출력 결과."""
    tuning_id: str
    changes: list[ParameterChange]
    status: TuningStatus
    monitoring_until: datetime | None


@dataclass
class GuardrailResult:
    """Guardrails 검증 결과."""
    passed: bool
    violations: list[str]
    clamped_changes: list[ParameterChange]     # 클램핑 적용 후 변경값
    requires_approval: bool                     # True면 Tier 3 사람 승인 필요


@dataclass
class RollbackCheckResult:
    """롤백 모니터링 체크 결과."""
    action: str                                # "continue" | "rollback" | "confirm" | "suspend"
    reason: str


@dataclass
class TuningSessionResult:
    """튜닝 세션 전체 결과."""
    tuning_id: str
    strategy_id: str
    tier: TierLevel
    status: TuningStatus
    changes: list[ParameterChange]
    eval_metrics: EvalMetrics | None
    reason: str
```

---

## 5. DB 스키마

기존 `_SCHEMA`에 2개 테이블 추가. `sqlite_store.py`와 `postgres_store.py` 양쪽에 동일 적용.

### 5.1 tuning_history

```sql
CREATE TABLE IF NOT EXISTS tuning_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tuning_id       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    strategy_id     TEXT NOT NULL,
    tier            TEXT NOT NULL,
    parameter_name  TEXT NOT NULL,
    old_value       REAL NOT NULL,
    new_value       REAL NOT NULL,
    change_pct      REAL NOT NULL,
    reason          TEXT NOT NULL,
    eval_window     TEXT NOT NULL,
    eval_pf         REAL,
    eval_mdd        REAL,
    eval_winrate    REAL,
    validation_pf   REAL,
    validation_mdd  REAL,
    llm_provider    TEXT,
    llm_model       TEXT,
    llm_diagnosis   TEXT,
    llm_confidence  TEXT,
    status          TEXT NOT NULL DEFAULT 'applied',
    rollback_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_tuning_history_strategy
    ON tuning_history(strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tuning_history_status
    ON tuning_history(status);
```

### 5.2 tuning_report

```sql
CREATE TABLE IF NOT EXISTS tuning_report (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tuning_id       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    eval_window     TEXT NOT NULL,
    strategy_id     TEXT NOT NULL,
    regime          TEXT,
    total_trades    INTEGER,
    win_rate        REAL,
    profit_factor   REAL,
    max_drawdown    REAL,
    avg_r_multiple  REAL,
    signal_accuracy REAL,
    recommendations TEXT,
    applied_changes TEXT
);

CREATE INDEX IF NOT EXISTS idx_tuning_report_strategy
    ON tuning_report(strategy_id, created_at DESC);
```

**설계 결정:** 각 `ParameterChange`는 `tuning_history`에 개별 행으로 저장한다 (같은 `tuning_id`로 그룹화). 이는 파라미터별 변경 추이를 쿼리하기 용이하다.

---

## 6. 설정 클래스

**파일:** `engine/tuner/config.py`

```python
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from engine.tuner.enums import TierLevel
from engine.tuner.models import ParameterBounds


# ── LLM 프로바이더 설정 ──

class LLMProviderSettings(BaseSettings):
    model_config = {"env_prefix": "TUNER_"}

    llm_primary: str = "claude"
    llm_fallback: str = "openai"
    llm_degraded_enabled: bool = True

    # Claude
    claude_model: str = "claude-sonnet-4-20250514"
    claude_timeout: int = 30

    # OpenAI
    openai_model: str = "gpt-4o"
    openai_timeout: int = 30

    # 비용 관리
    monthly_budget_usd: float = 5.0
    budget_warning_pct: float = 0.8

    # Circuit Breaker
    cb_failure_threshold: int = 3
    cb_recovery_timeout_min: int = 10


# ── 스케줄 설정 ──

class TunerScheduleSettings(BaseSettings):
    model_config = {"env_prefix": "TUNER_"}

    # Tier 1: 주간
    tier1_cron_day: str = "mon"
    tier1_cron_hour: int = 0          # UTC
    tier1_eval_days: int = 7
    tier1_min_trades: int = 3

    # Tier 2: 격주
    tier2_interval_weeks: int = 2
    tier2_eval_days: int = 14
    tier2_min_trades: int = 5

    # Tier 3: 월간
    tier3_interval_weeks: int = 4
    tier3_eval_days: int = 30
    tier3_min_trades: int = 10


# ── 가드레일 설정 ──

class GuardrailSettings(BaseSettings):
    model_config = {"env_prefix": "TUNER_"}

    max_change_pct: float = 0.20           # 1회 최대 변경 비율
    monitoring_hours: int = 48             # 모니터링 기간
    mdd_rollback_multiplier: float = 2.0   # MDD 악화 배수 → 롤백
    max_consecutive_rollbacks: int = 3     # 연속 롤백 → 일시 중단
    consecutive_loss_rollback: int = 5     # 연속 손실 → 롤백

    # Optuna
    optuna_n_trials: int = 50
    optuna_top_k: int = 3

    # Walk-Forward
    wf_train_bars: int = 1440              # 60일 × 24h
    wf_test_bars: int = 720                # 30일 × 24h


# ── 루트 설정 ──

class TunerSettings(BaseSettings):
    """engine/config/settings.py의 AppSettings에 통합되는 튜너 설정."""
    model_config = {
        "env_prefix": "TUNER_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    enabled: bool = False                   # opt-in: 기본 비활성화
    llm: LLMProviderSettings = Field(default_factory=LLMProviderSettings)
    schedule: TunerScheduleSettings = Field(default_factory=TunerScheduleSettings)
    guardrails: GuardrailSettings = Field(default_factory=GuardrailSettings)
```

### 파라미터 범위 레지스트리

```python
# engine/tuner/config.py 하단

TIER_1_BOUNDS: list[ParameterBounds] = [
    ParameterBounds("buy_threshold",  TierLevel.TIER_1, 0.03, 0.25),
    ParameterBounds("sell_threshold", TierLevel.TIER_1, -0.20, -0.02),
    ParameterBounds("tf_weight_1h",   TierLevel.TIER_1, 0.1, 0.8),
    ParameterBounds("tf_weight_4h",   TierLevel.TIER_1, 0.1, 0.8),
    ParameterBounds("tf_weight_1d",   TierLevel.TIER_1, 0.0, 0.8),
    ParameterBounds("macro_weight",   TierLevel.TIER_1, 0.0, 0.30),
    ParameterBounds("score_w1",       TierLevel.TIER_1, 0.10, 0.60),
    ParameterBounds("score_w2",       TierLevel.TIER_1, 0.10, 0.60),
    ParameterBounds("score_w3",       TierLevel.TIER_1, 0.10, 0.60),
]

TIER_2_BOUNDS: list[ParameterBounds] = [
    ParameterBounds("atr_stop_multiplier",         TierLevel.TIER_2, 1.5, 3.0),
    ParameterBounds("reward_risk_ratio",            TierLevel.TIER_2, 1.5, 4.0),
    ParameterBounds("trailing_stop_activation_pct", TierLevel.TIER_2, 0.005, 0.03),
    ParameterBounds("trailing_stop_distance_pct",   TierLevel.TIER_2, 0.008, 0.03),
    ParameterBounds("max_position_pct",             TierLevel.TIER_2, 0.05, 0.30),
    ParameterBounds("volatility_cap_pct",           TierLevel.TIER_2, 0.05, 0.12),
    ParameterBounds("daily_max_loss_pct",           TierLevel.TIER_2, 0.03, 0.08),
]

TIER_3_BOUNDS: list[ParameterBounds] = [
    ParameterBounds("adx_trend_threshold",    TierLevel.TIER_3, 20.0, 35.0),
    ParameterBounds("bb_width_vol_threshold", TierLevel.TIER_3, 0.02, 0.08),
    ParameterBounds("debounce_count",         TierLevel.TIER_3, 2.0, 5.0),
    ParameterBounds("cooldown_minutes",       TierLevel.TIER_3, 30.0, 120.0),
]

ALL_BOUNDS: dict[str, ParameterBounds] = {
    b.name: b for b in TIER_1_BOUNDS + TIER_2_BOUNDS + TIER_3_BOUNDS
}
```

### AppSettings 통합

```python
# engine/config/settings.py에 추가
class AppSettings(BaseSettings):
    ...
    tuner: TunerSettings = Field(default_factory=TunerSettings)
```

### 환경변수

```bash
# .env 추가 항목

# AI Tuner 활성화
TUNER_ENABLED=false

# LLM 프로바이더
TUNER_LLM_PRIMARY=claude
TUNER_LLM_FALLBACK=openai
TUNER_LLM_DEGRADED_ENABLED=true

# Claude API
ANTHROPIC_API_KEY=sk-ant-...
TUNER_CLAUDE_MODEL=claude-sonnet-4-20250514
TUNER_CLAUDE_TIMEOUT=30

# OpenAI API (fallback)
OPENAI_API_KEY=sk-...
TUNER_OPENAI_MODEL=gpt-4o
TUNER_OPENAI_TIMEOUT=30

# 비용 관리
TUNER_MONTHLY_BUDGET_USD=5.0
TUNER_BUDGET_WARNING_PCT=0.8

# Circuit Breaker
TUNER_CB_FAILURE_THRESHOLD=3
TUNER_CB_RECOVERY_TIMEOUT_MIN=10

# Guardrails
TUNER_MAX_CHANGE_PCT=0.20
TUNER_MONITORING_HOURS=48
TUNER_MDD_ROLLBACK_MULTIPLIER=2.0
TUNER_MAX_CONSECUTIVE_ROLLBACKS=3
```

---

## 7. 핵심 인터페이스

### 7.1 LLMClient Protocol

**파일:** `engine/tuner/llm_client.py`

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from engine.tuner.models import LLMResponse


@runtime_checkable
class LLMClient(Protocol):
    """LLM 프로바이더 클라이언트 프로토콜."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse: ...


class ClaudeLLMClient:
    """Anthropic Claude API 클라이언트. httpx 직접 호출."""

    def __init__(self, api_key: str, model: str, timeout: int = 30) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """
        POST https://api.anthropic.com/v1/messages
        Headers: x-api-key, anthropic-version: 2023-06-01
        Body: model, max_tokens, system, messages[{role: "user", content}]
        비용 계산: input_tokens * 0.003/1000 + output_tokens * 0.015/1000
        """
        ...


class OpenAILLMClient:
    """OpenAI API 클라이언트. httpx 직접 호출."""

    def __init__(self, api_key: str, model: str, timeout: int = 30) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """
        POST https://api.openai.com/v1/chat/completions
        Headers: Authorization: Bearer {api_key}
        Body: model, max_tokens, temperature, messages[{role, content}]
        비용 계산: input_tokens * 0.005/1000 + output_tokens * 0.015/1000
        """
        ...
```

**설계 결정:** SDK(anthropic, openai) 대신 httpx 직접 호출. 기존 `TelegramNotifier` 패턴과 일치하며, 의존성 최소화.

### 7.2 ProviderRouter

**파일:** `engine/tuner/provider_router.py`

```python
from __future__ import annotations

import time
from enum import StrEnum
from dataclasses import dataclass

from engine.tuner.llm_client import LLMClient
from engine.tuner.models import LLMResponse


class CBState(StrEnum):
    CLOSED = "closed"           # 정상
    OPEN = "open"               # 차단
    HALF_OPEN = "half_open"     # 복구 시도


class LLMCircuitBreaker:
    """프로바이더별 Circuit Breaker. 기존 engine/execution/circuit_breaker.py 패턴 재사용."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_seconds: float = 600.0,
    ) -> None: ...

    @property
    def state(self) -> CBState: ...

    def allow_request(self) -> bool:
        """
        CLOSED → 항상 허용
        OPEN → recovery_seconds 경과 시 HALF_OPEN 전환 후 허용
        HALF_OPEN → 1회만 허용
        """
        ...

    def record_success(self) -> None:
        """HALF_OPEN → CLOSED 전환. 실패 카운트 초기화."""
        ...

    def record_failure(self) -> None:
        """
        실패 카운트 증가.
        failure_count >= failure_threshold → OPEN 전환.
        HALF_OPEN에서 실패 → 다시 OPEN.
        """
        ...


class CostTracker:
    """월간 LLM API 비용 추적."""

    def __init__(
        self,
        monthly_budget_usd: float,
        warning_pct: float = 0.8,
    ) -> None: ...

    def record_cost(self, cost_usd: float, provider: str) -> None: ...
    def is_budget_exceeded(self) -> bool: ...
    def is_budget_warning(self) -> bool: ...
    def get_monthly_usage(self) -> dict[str, float]: ...
    def reset_monthly(self) -> None: ...


class ProviderRouter:
    """LLM 프로바이더 체인 라우터."""

    def __init__(
        self,
        providers: list[LLMClient],
        circuit_breakers: dict[str, LLMCircuitBreaker],
        cost_tracker: CostTracker,
        degraded_enabled: bool = True,
    ) -> None: ...

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> LLMResponse | None:
        """
        프로바이더 우선순위 순서로 시도:
        1. 각 프로바이더에 대해:
           a. circuit_breaker.allow_request() 확인
           b. cost_tracker.is_budget_exceeded() 확인
           c. API 호출 시도
           d. 성공 → record_success(), record_cost(), 응답 반환
           e. 실패 → record_failure(), 다음 프로바이더로
        2. 모든 프로바이더 실패:
           a. degraded_enabled → None 반환 (호출자가 DegradedFallback 사용)
           b. degraded_disabled → raise AllProvidersFailedError
        """
        ...

    @property
    def active_provider(self) -> str: ...

    @property
    def is_degraded(self) -> bool: ...

    def get_provider_status(self) -> dict[str, dict]:
        """
        반환 형식:
        {
            "claude": {"state": "closed", "failures": 0, "cost_usd": 0.05},
            "openai": {"state": "open", "failures": 3, "cost_usd": 0.00},
            "budget": {"used_usd": 0.05, "limit_usd": 5.0, "warning": false}
        }
        """
        ...
```

### 7.3 StrategyEvaluator

**파일:** `engine/tuner/evaluator.py`

```python
from __future__ import annotations

from datetime import datetime

from shared.protocols import DataStore, Notifier
from engine.tuner.models import EvalMetrics, EvaluationResult, LLMDiagnosis, ParamRecommendation
from engine.tuner.provider_router import ProviderRouter
from engine.tuner.degraded import DegradedFallback
from engine.tuner.store import TunerStore


class StrategyEvaluator:
    """전략 성과 평가 + LLM 진단."""

    def __init__(
        self,
        data_store: DataStore,
        tuner_store: TunerStore,
        provider_router: ProviderRouter,
        degraded: DegradedFallback,
        notifier: Notifier | None = None,
    ) -> None: ...

    async def evaluate(
        self,
        strategy_id: str,
        eval_days: int = 7,
        now: datetime | None = None,
    ) -> EvaluationResult:
        """
        1. DataStore에서 eval_window 기간의 주문/포지션/시그널 조회
        2. compute_metrics() (engine/strategy/backtest/metrics.py 재사용)로 EvalMetrics 계산
        3. 최소 거래 건수 미달 → should_tune=False, skip_reason="insufficient_trades"
        4. 성과 양호 (PF > 1.5, win_rate > 0.4) → should_tune=False, skip_reason="metrics_acceptable"
        5. DegradedFallback.diagnose()로 rule_diagnosis 항상 계산
        6. ProviderRouter.complete(DIAGNOSIS_TEMPLATE)로 LLM 진단
           → 성공: LLMDiagnosis 파싱
           → 실패/None: diagnosis=None (rule_diagnosis가 대체)
        7. TunerStore.save_tuning_report()
        8. EvaluationResult 반환
        """
        ...

    def _compute_signal_accuracy(
        self,
        signals: list,
        candles: list,
        lookahead_bars: int = 24,
    ) -> float:
        """BUY 시그널 후 lookahead_bars 내 1% 이상 상승 비율."""
        ...
```

### 7.4 HybridOptimizer

**파일:** `engine/tuner/optimizer.py`

```python
from __future__ import annotations

from typing import Any, Callable

import optuna
import pandas as pd

from shared.protocols import DataStore, ExchangeClient
from engine.tuner.enums import TierLevel
from engine.tuner.models import (
    EvaluationResult,
    OptimizerCandidate,
    OptimizationResult,
    TuningDecision,
)
from engine.tuner.config import ALL_BOUNDS, GuardrailSettings
from engine.tuner.provider_router import ProviderRouter
from engine.tuner.degraded import DegradedFallback
from engine.tuner.guardrails import Guardrails


class HybridOptimizer:
    """Optuna 베이지안 최적화 + LLM 후보 선택."""

    def __init__(
        self,
        data_store: DataStore,
        exchange_client: ExchangeClient,
        provider_router: ProviderRouter,
        degraded: DegradedFallback,
        guardrails: Guardrails,
        config: GuardrailSettings,
    ) -> None: ...

    async def optimize(
        self,
        strategy_id: str,
        evaluation: EvaluationResult,
        tier: TierLevel,
        current_params: dict[str, float],
    ) -> OptimizationResult:
        """
        1. LLM 진단의 recommended_params로 탐색 범위 결정
           (추천 파라미터 중심으로 ±20% 범위 설정)
        2. 해당 tier의 bounds에서 탐색 공간 구성
        3. 과거 캔들 데이터 수집 (wf_train_bars + wf_test_bars)
        4. Optuna study 생성 + optimize(n_trials)
           → 각 trial: WalkForward 백테스트 실행, PF를 목적함수로
        5. 상위 top_k 후보 선정
        6. ProviderRouter.complete(CANDIDATE_SELECTION_TEMPLATE)로 최적 후보 선택
           → 실패: DegradedFallback.select_candidate() 사용
        7. 안전 검증: 선택된 후보로 최근 30일 BacktestEngine 실행
           → MDD 악화 또는 PF < 1.0 → 거부
        8. ProviderRouter.complete(APPROVAL_TEMPLATE)로 최종 승인
           → 실패: DegradedFallback.approve() 사용
        9. OptimizationResult 반환
        """
        ...

    def _create_optuna_objective(
        self,
        strategy_id: str,
        tier: TierLevel,
        current_params: dict[str, float],
        ohlcv_by_tf: dict[str, pd.DataFrame],
    ) -> Callable[[optuna.Trial], float]:
        """
        Optuna 목적함수 생성.

        Trial에서 파라미터를 샘플링하고 WalkForwardEngine으로 검증.
        반환값: validation_pf (최대화 목표)

        파라미터 제약:
        - tf_weights 합계 = 1.0 (정규화 적용)
        - score_weights 합계 = 1.0 (정규화 적용)
        - 각 값은 ParameterBounds 범위 내
        """
        ...

    def _narrow_bounds(
        self,
        current_value: float,
        bounds: "ParameterBounds",
        max_change_pct: float,
    ) -> tuple[float, float]:
        """
        현재 값 기준 ±max_change_pct 범위와 절대 범위의 교집합.
        예: current=0.10, max_change=20%, bounds=(0.03, 0.25)
            → narrow=(0.08, 0.12)
        """
        ...
```

### 7.5 ParameterApplier

**파일:** `engine/tuner/applier.py`

```python
from __future__ import annotations

from datetime import datetime

from shared.protocols import Notifier
from engine.strategy.signal import SignalGenerator
from engine.strategy.risk import RiskEngine
from engine.strategy.regime_switch import RegimeSwitchManager
from engine.tuner.models import (
    ApplyResult,
    OptimizationResult,
    EvaluationResult,
    ParameterChange,
    TuningHistoryRecord,
)
from engine.tuner.enums import TierLevel, TuningStatus
from engine.tuner.store import TunerStore
from engine.tuner.guardrails import Guardrails


class ParameterApplier:
    """파라미터 반영 + 이력 저장 + 롤백."""

    def __init__(
        self,
        tuner_store: TunerStore,
        notifier: Notifier | None,
        guardrails: Guardrails,
    ) -> None: ...

    async def apply(
        self,
        strategy_id: str,
        optimization: OptimizationResult,
        evaluation: EvaluationResult,
        signal_generator: SignalGenerator,
        risk_engine: RiskEngine | None = None,
        regime_switch_manager: RegimeSwitchManager | None = None,
    ) -> ApplyResult:
        """
        1. Guardrails.validate_changes() → 클램핑 + 위반 검사
        2. requires_approval이면 → status=PENDING, 텔레그램 알림 후 반환
        3. Tier 1 반영: SignalGenerator 속성 직접 변경
           signal_gen.buy_threshold = new_value
           signal_gen.sell_threshold = new_value
           signal_gen.tf_weights = {tf: weight for ...}
           signal_gen.macro_weight = new_value
           signal_gen.score_weights = ScoreWeights(w1, w2, w3)
        4. Tier 2 반영: RiskEngine.config 새 인스턴스로 교체
           risk_engine.config = RiskConfig(
               atr_stop_multiplier=...,
               reward_risk_ratio=...,
               ...
           )
        5. Tier 3 반영: RegimeSwitchManager 설정 교체
        6. TunerStore.save_tuning_history(status=MONITORING)
        7. 텔레그램 알림: 변경 요약 + LLM 모델명
        8. ApplyResult 반환 (monitoring_until = now + 48h)
        """
        ...

    async def rollback(
        self,
        tuning_id: str,
        signal_generator: SignalGenerator,
        risk_engine: RiskEngine | None = None,
        regime_switch_manager: RegimeSwitchManager | None = None,
        reason: str = "auto_rollback",
    ) -> bool:
        """
        1. TunerStore에서 tuning_id의 old_value 조회
        2. 각 파라미터를 old_value로 복원
        3. TunerStore.update_tuning_status(ROLLED_BACK)
        4. 텔레그램 알림
        5. True/False 반환
        """
        ...
```

**Tier 1 반영 상세:**

`SignalGenerator`의 `apply_preset()` 메서드가 프리셋 전체를 교체하는 반면, AI Tuner는 개별 속성만 변경한다. `SignalGenerator`의 관련 속성들:

| 속성 | 타입 | 변경 방식 |
|------|------|----------|
| `buy_threshold` | `float` | 직접 할당 |
| `sell_threshold` | `float` | 직접 할당 |
| `tf_weights` | `dict[str, float]` | dict 재할당 |
| `macro_weight` | `float` | 직접 할당 |
| `score_weights` | `ScoreWeights` | 새 인스턴스 생성 후 할당 |

**Tier 2 반영 상세:**

`RiskConfig`는 `frozen=True`이므로 새 인스턴스를 생성해야 한다. `RiskEngine.config`는 일반 속성이므로 재할당 가능:

```python
from dataclasses import replace
new_config = replace(risk_engine.config, **new_params_dict)
risk_engine.config = new_config
```

단, `replace()`는 `frozen=True`에서도 새 인스턴스를 생성하므로 안전.

### 7.6 Guardrails

**파일:** `engine/tuner/guardrails.py`

```python
from __future__ import annotations

from engine.tuner.config import ALL_BOUNDS, GuardrailSettings
from engine.tuner.enums import DiagnosisDirection, TierLevel
from engine.tuner.models import GuardrailResult, ParameterChange, ParameterBounds
from engine.tuner.store import TunerStore


class Guardrails:
    """파라미터 변경 안전 규칙."""

    def __init__(self, config: GuardrailSettings, tuner_store: TunerStore) -> None: ...

    async def validate_changes(
        self,
        changes: list[ParameterChange],
        strategy_id: str,
    ) -> GuardrailResult:
        """
        검증 규칙:
        1. 각 변경의 |change_pct| <= max_change_pct (초과 시 클램핑)
        2. 각 값이 ParameterBounds.min_value~max_value 범위 내
        3. tf_weights 합계 = 1.0 (정규화 적용)
        4. score_weights 합계 = 1.0 (정규화 적용)
        5. Tier 2: 직전 변경과 같은 방향 금지 (check_tier2_direction)
        6. Tier 3 포함 시: requires_approval = True

        반환: GuardrailResult(passed, violations, clamped_changes, requires_approval)
        """
        ...

    def clamp_change(
        self,
        param_name: str,
        old_value: float,
        proposed_value: float,
        bounds: ParameterBounds,
    ) -> float:
        """
        제안 값을 안전 범위로 클램핑:
        1. max_change = old_value * bounds.max_change_pct
        2. clamped = clamp(proposed, old - max_change, old + max_change)
        3. clamped = clamp(clamped, bounds.min_value, bounds.max_value)
        """
        ...

    async def check_tier2_direction(
        self,
        strategy_id: str,
        param_name: str,
        direction: DiagnosisDirection,
    ) -> bool:
        """
        tuning_history에서 해당 파라미터의 마지막 변경 방향 조회.
        같은 방향이면 False (차단), 다르면 True (허용).
        이력 없으면 True.
        """
        ...

    @staticmethod
    def normalize_weights(
        changes: list[ParameterChange],
        prefix: str,
    ) -> list[ParameterChange]:
        """
        tf_weight_* 또는 score_w* 그룹의 합계가 1.0이 되도록 정규화.
        """
        ...
```

### 7.7 RollbackMonitor

**파일:** `engine/tuner/rollback.py`

```python
from __future__ import annotations

from shared.protocols import DataStore, Notifier
from engine.strategy.signal import SignalGenerator
from engine.strategy.risk import RiskEngine
from engine.strategy.regime_switch import RegimeSwitchManager
from engine.tuner.models import RollbackCheckResult
from engine.tuner.config import GuardrailSettings
from engine.tuner.store import TunerStore
from engine.tuner.applier import ParameterApplier


class RollbackMonitor:
    """48시간 모니터링 + 자동 롤백."""

    def __init__(
        self,
        data_store: DataStore,
        tuner_store: TunerStore,
        applier: ParameterApplier,
        notifier: Notifier | None,
        config: GuardrailSettings,
    ) -> None: ...

    async def check(
        self,
        tuning_id: str,
        strategy_id: str,
        signal_generator: SignalGenerator,
        risk_engine: RiskEngine | None = None,
        regime_switch_manager: RegimeSwitchManager | None = None,
    ) -> RollbackCheckResult:
        """
        매 시간 호출. 활성 모니터링 세션에 대해:

        1. tuning_history에서 적용 시점(created_at) 조회
        2. 적용 이후 포지션/PnL 데이터 조회
        3. 현재 MDD 계산 vs 튜닝 전 MDD (eval_mdd)
        4. 판단:
           a. monitoring_until 경과 + 이상 없음 → "confirm"
           b. current_mdd > eval_mdd * mdd_rollback_multiplier → "rollback"
           c. consecutive_losses > consecutive_loss_rollback → "rollback"
           d. 그 외 → "continue"

        5. "rollback" 시:
           - ParameterApplier.rollback() 호출
           - _consecutive_rollback_count += 1
           - count >= max_consecutive_rollbacks → "suspend"
        """
        ...

    @property
    def active_sessions(self) -> list[str]: ...

    @property
    def consecutive_rollback_count(self) -> int: ...

    def reset_rollback_count(self) -> None: ...
```

### 7.8 TunerPipeline

**파일:** `engine/tuner/pipeline.py`

```python
from __future__ import annotations

from shared.protocols import Notifier
from engine.tuner.enums import TierLevel, TunerState, TuningStatus
from engine.tuner.models import TuningSessionResult
from engine.tuner.config import TunerSettings
from engine.tuner.evaluator import StrategyEvaluator
from engine.tuner.optimizer import HybridOptimizer
from engine.tuner.applier import ParameterApplier
from engine.tuner.rollback import RollbackMonitor


class TunerPipeline:
    """전체 튜닝 파이프라인 오케스트레이터."""

    def __init__(
        self,
        evaluator: StrategyEvaluator,
        optimizer: HybridOptimizer,
        applier: ParameterApplier,
        rollback_monitor: RollbackMonitor,
        notifier: Notifier | None,
        config: TunerSettings,
    ) -> None:
        self._state: TunerState = TunerState.IDLE

    async def run_tuning_session(
        self,
        strategy_id: str,
        tier: TierLevel = TierLevel.TIER_1,
    ) -> TuningSessionResult:
        """
        단일 전략에 대한 튜닝 세션 실행.

        1. state 검사: SUSPENDED이면 스킵
        2. state = EVALUATING
        3. StrategyEvaluator.evaluate()
           → should_tune=False이면 스킵, 텔레그램 보고
        4. state = OPTIMIZING
        5. HybridOptimizer.optimize()
           → decision.approved=False이면 스킵, 기록
        6. state = APPLYING
        7. ParameterApplier.apply()
           → requires_approval이면 PENDING 상태로 반환
        8. state = MONITORING
        9. 텔레그램 요약 알림 (LLM으로 생성 또는 템플릿)
        10. TuningSessionResult 반환
        """
        ...

    async def run_scheduled_tuning(self) -> list[TuningSessionResult]:
        """
        스케줄러에서 호출. 활성 전략 ID 목록에 대해 run_tuning_session() 순차 실행.
        Tier는 스케줄 설정에 따라 결정:
        - 매주: Tier 1
        - 격주 (짝수 주): Tier 1 + Tier 2
        - 매월 (4주째): Tier 1 + Tier 2 + Tier 3
        """
        ...

    async def check_monitoring(self) -> None:
        """
        스케줄러에서 매 시간 호출.
        RollbackMonitor.active_sessions 순회하며 check() 호출.
        "suspend" 반환 시 → state = SUSPENDED, 텔레그램 알림.
        """
        ...

    async def manual_rollback(self, tuning_id: str) -> bool:
        """API/텔레그램에서 수동 롤백 요청."""
        ...

    async def approve_tier3(self, tuning_id: str, approved: bool) -> bool:
        """Tier 3 PENDING 상태의 변경을 승인/거부."""
        ...

    @property
    def state(self) -> TunerState: ...
```

### 7.9 TunerStore

**파일:** `engine/tuner/store.py`

```python
from __future__ import annotations

from datetime import datetime

from shared.protocols import DataStore
from engine.tuner.enums import DiagnosisDirection, TuningStatus
from engine.tuner.models import TuningHistoryRecord, TuningReport


class TunerStore:
    """튜닝 테이블 DB 접근 레이어. DataStore의 내부 커넥션을 사용."""

    def __init__(self, data_store: DataStore) -> None:
        """
        DataStore 인스턴스를 받아 내부 DB 커넥션에 접근.
        SQLite: data_store._db (aiosqlite.Connection)
        Postgres: data_store._pool (asyncpg.Pool)
        """
        ...

    async def save_tuning_history(self, record: TuningHistoryRecord) -> None:
        """
        record.changes의 각 ParameterChange를 개별 행으로 INSERT.
        같은 tuning_id로 그룹화.
        """
        ...

    async def save_tuning_report(self, report: TuningReport) -> None:
        """tuning_report 테이블에 INSERT. recommendations, applied_changes는 JSON 직렬화."""
        ...

    async def get_tuning_history(
        self,
        strategy_id: str | None = None,
        status: TuningStatus | None = None,
        limit: int = 50,
    ) -> list[TuningHistoryRecord]: ...

    async def get_latest_tuning(self, strategy_id: str) -> TuningHistoryRecord | None: ...

    async def update_tuning_status(
        self,
        tuning_id: str,
        status: TuningStatus,
        rollback_at: datetime | None = None,
    ) -> None: ...

    async def get_last_change_direction(
        self,
        strategy_id: str,
        parameter_name: str,
    ) -> DiagnosisDirection | None:
        """Tier 2 연속 동방향 검사용. 가장 최근 변경의 방향 반환."""
        ...

    async def count_consecutive_rollbacks(self, strategy_id: str) -> int:
        """가장 최근의 연속 rolled_back 상태 개수."""
        ...

    async def get_monitoring_sessions(self) -> list[TuningHistoryRecord]:
        """status='monitoring'인 모든 레코드 반환."""
        ...
```

**설계 결정:** DataStore Protocol을 확장하지 않고 별도 래퍼로 구현. 이유:
- DataStore Protocol 변경 시 SQLite/Postgres 양쪽 구현체를 수정해야 함
- 튜닝 테이블은 튜너 모듈에서만 사용하므로 결합도를 낮춤
- 내부 커넥션 직접 접근은 기존 패턴과 일치 (analytics_store 등)

---

## 8. LLM 프롬프트 템플릿

**파일:** `engine/tuner/prompts.py`

### 8.1 System Prompt

```python
SYSTEM_PROMPT = (
    "You are a BTC/KRW automated trading strategy analyst. "
    "You analyze strategy performance metrics and recommend parameter adjustments. "
    "Always respond in valid JSON format. Do not include markdown code fences."
)
```

### 8.2 진단 프롬프트 (DIAGNOSIS_TEMPLATE)

```python
DIAGNOSIS_TEMPLATE = """\
Below are the performance metrics for strategy {strategy_id} ({strategy_name}) \
over the past {eval_days} days:

- Regime: {regime}
- Total trades: {total_trades}
- Win rate: {win_rate:.1%}
- Profit Factor: {profit_factor:.2f}
- Max Drawdown: {max_drawdown:.2%}
- Avg R-multiple: {avg_r_multiple:.2f}
- Avg holding time: {avg_holding_hours:.1f}h
- Signal accuracy: {signal_accuracy:.1%}
- Total return: {total_return_pct:.2%}
- Current parameters: {current_params_json}

Analyze:
1. Root cause of underperformance (1-2 causes, be specific)
2. Which Tier {tier} parameters to adjust (from: {adjustable_params})
3. Direction (increase/decrease) and reasoning

Respond in JSON:
{{
  "root_causes": ["cause1", "cause2"],
  "recommended_params": [
    {{"name": "param_name", "direction": "increase|decrease", "reason": "..."}}
  ],
  "confidence": "high|medium|low"
}}"""
```

### 8.3 후보 선택 프롬프트 (CANDIDATE_SELECTION_TEMPLATE)

```python
CANDIDATE_SELECTION_TEMPLATE = """\
Optuna generated {n_candidates} parameter candidates for {strategy_id}:

{candidates_text}

Current market context:
- Regime: {regime} (lasted {regime_duration}h)
- 7d BTC/KRW price range: {btc_range}
- Recent volume vs 20d average: {volume_ratio:.0%}
- Current ADX: {adx:.1f}, BB Width: {bb_width:.4f}

Select the best candidate considering:
1. Risk-adjusted performance (PF vs MDD tradeoff)
2. Trade frequency (too few = unreliable, too many = overtrading)
3. Current market conditions

Respond in JSON:
{{
  "selected_candidate_id": "candidate_id",
  "reasoning": "explanation",
  "risk_assessment": "assessment of downside risk",
  "confidence": "high|medium|low"
}}"""
```

### 8.4 승인 프롬프트 (APPROVAL_TEMPLATE)

```python
APPROVAL_TEMPLATE = """\
Safety validation results for {strategy_id} parameter change:

Proposed changes:
{changes_text}

30-day simulation results:
- PF: {sim_pf:.2f} (baseline: {base_pf:.2f})
- MDD: {sim_mdd:.2%} (baseline: {base_mdd:.2%})
- Trades: {sim_trades} (baseline: {base_trades})
- Win rate: {sim_win_rate:.1%} (baseline: {base_win_rate:.1%})

Should this change be approved? Consider:
1. Is the improvement statistically significant given {sim_trades} trades?
2. Is the MDD acceptable relative to the improvement?
3. Are there signs of overfitting (e.g., profit from few outlier trades)?

Respond in JSON:
{{
  "approved": true|false,
  "reason": "detailed justification",
  "confidence": "high|medium|low"
}}"""
```

### 8.5 요약 프롬프트 (SUMMARY_TEMPLATE)

```python
SUMMARY_TEMPLATE = """\
Summarize this tuning session in 2-3 Korean sentences for the operator:
Strategy: {strategy_id}
Changes: {changes_text}
Before: PF={old_pf:.2f}, Win={old_win:.1%}, MDD={old_mdd:.2%}
After (simulated): PF={new_pf:.2f}, Win={new_win:.1%}, MDD={new_mdd:.2%}
LLM diagnosis: {diagnosis_summary}"""
```

### 8.6 응답 파싱

```python
import json
import re


def parse_llm_json(text: str) -> dict:
    """
    LLM 응답에서 JSON 추출 및 파싱.
    1. text를 직접 json.loads() 시도
    2. 실패 시 ```json ... ``` 코드 블록에서 추출
    3. 실패 시 첫 번째 { ... } 블록 추출 (중첩 고려)
    4. 모두 실패 시 ValueError 발생
    """
    ...
```

---

## 9. Degraded Mode

**파일:** `engine/tuner/degraded.py`

```python
from __future__ import annotations

from engine.tuner.enums import DiagnosisDirection, LLMConfidence
from engine.tuner.models import EvalMetrics, OptimizerCandidate, ParamRecommendation


class DegradedFallback:
    """LLM 전체 장애 시 규칙 기반 대체 로직."""

    def diagnose(
        self,
        metrics: EvalMetrics,
        current_params: dict[str, float],
    ) -> list[ParamRecommendation]:
        """
        규칙 기반 진단. 항상 confidence=LOW.

        규칙:
        1. win_rate < 0.30 → buy_threshold INCREASE
           (진입 기준이 너무 낮아 노이즈에 반응)
        2. win_rate > 0.70 and profit_factor < 1.5 → reward_risk_ratio INCREASE
           (승률은 높지만 수익이 작음 → TP를 넓혀야)
        3. avg_holding_hours < 3.0 → sell_threshold DECREASE (절대값 감소)
           (보유 시간이 너무 짧음 → 조기 청산 방지)
        4. signal_accuracy < 0.20 → buy_threshold INCREASE
           (시그널 정확도 낮음 → 진입 기준 강화)
        5. max_drawdown > 0.05 → max_position_pct DECREASE
           (낙폭이 큼 → 포지션 축소)
        6. avg_r_multiple < 0.5 → atr_stop_multiplier INCREASE
           (R배수 낮음 → SL이 너무 가까움)
        """
        ...

    def select_candidate(
        self,
        candidates: list[OptimizerCandidate],
    ) -> OptimizerCandidate:
        """검증 PF가 가장 높은 후보 선택."""
        return max(candidates, key=lambda c: c.validation_pf)

    def approve(
        self,
        candidate: OptimizerCandidate,
        baseline_pf: float,
        baseline_mdd: float,
    ) -> bool:
        """
        승인 조건:
        1. validation_pf >= 1.0
        2. validation_mdd <= baseline_mdd * 1.5
        """
        return (
            candidate.validation_pf >= 1.0
            and candidate.validation_mdd <= baseline_mdd * 1.5
        )
```

---

## 10. 파이프라인 흐름도

### 10.1 정상 경로

```
Scheduler (cron: Mon 00:00 UTC)
    │
    ▼
TunerPipeline.run_scheduled_tuning()
    │
    ├── 각 활성 strategy_id에 대해:
    │
    ▼
StrategyEvaluator.evaluate(strategy_id, eval_days=7)
    ├── DataStore 쿼리: 주문/포지션/시그널 (7일)
    ├── compute_metrics() → EvalMetrics
    ├── DegradedFallback.diagnose() → rule_diagnosis (항상)
    ├── ProviderRouter.complete(DIAGNOSIS) → LLMDiagnosis
    └── TunerStore.save_tuning_report()
    │
    ├── [should_tune == False] → 스킵, 텔레그램 "성과 양호"
    │
    ▼
HybridOptimizer.optimize(strategy_id, evaluation, tier=TIER_1)
    ├── 탐색 범위 설정 (현재값 ±20% ∩ bounds)
    ├── 캔들 데이터 수집 (90일)
    ├── Optuna study.optimize(n_trials=50)
    │   └── 각 trial: WalkForward 백테스트 → PF
    ├── 상위 3개 후보 선정
    ├── ProviderRouter.complete(CANDIDATE_SELECTION) → 1개 선택
    ├── 안전 검증: BacktestEngine (최근 30일)
    │   ├── MDD 악화 → 거부
    │   └── PF < 1.0 → 거부
    └── ProviderRouter.complete(APPROVAL) → 최종 승인/거부
    │
    ├── [approved == False] → 스킵, 거부 사유 기록
    │
    ▼
ParameterApplier.apply(strategy_id, ...)
    ├── Guardrails.validate_changes() → 클램핑
    ├── 현재 파라미터 스냅샷 → tuning_history
    ├── SignalGenerator 속성 변경 (Tier 1)
    ├── RiskEngine.config 교체 (Tier 2)
    ├── RegimeSwitchManager 설정 교체 (Tier 3)
    ├── TunerStore.save_tuning_history(MONITORING)
    └── 텔레그램 알림: 변경 요약 + LLM 모델명
    │
    ▼
[48시간 모니터링 시작]
    │
    ▼
Scheduler (interval: 1h)
    │
    ▼
TunerPipeline.check_monitoring()
    │
    ▼
RollbackMonitor.check(tuning_id, ...)
    ├── 적용 이후 PnL/MDD 계산
    ├── "continue" → 다음 시간에 재확인
    ├── "confirm" → status=CONFIRMED, 텔레그램 확정 알림
    └── "rollback" → ParameterApplier.rollback()
                      → consecutive_rollback_count += 1
                      → count >= 3 → state=SUSPENDED, 텔레그램 경고
```

### 10.2 오류/Degraded 경로

```
ProviderRouter.complete()
    │
    ├── Claude 시도 → 실패 (timeout/4xx/5xx)
    │   └── CircuitBreaker("claude").record_failure()
    │
    ├── OpenAI 시도 → 실패
    │   └── CircuitBreaker("openai").record_failure()
    │
    └── 모든 프로바이더 실패:
        ├── degraded_enabled=True → None 반환
        │   └── 호출자가 DegradedFallback 메서드 사용
        │       └── llm_provider="degraded", llm_model=None 기록
        │       └── 텔레그램: "LLM 미사용 모드로 튜닝 수행"
        │
        └── degraded_enabled=False → AllProvidersFailedError
            └── 튜닝 세션 중단, 에러 기록
```

### 10.3 Tier 3 승인 흐름

```
Guardrails.validate_changes()
    │
    └── Tier 3 파라미터 감지 → requires_approval=True
        │
        ▼
    텔레그램 알림:
    "레짐 파라미터 변경 제안:
     debounce_count: 3 → 2
     cooldown_minutes: 60 → 45
     승인: /approve {tuning_id}
     거부: /reject {tuning_id}"
        │
        ▼
    [대기: API 또는 텔레그램 명령]
        │
        ├── /approve → TunerPipeline.approve_tier3(id, True)
        │   └── ParameterApplier.apply() 진행 → MONITORING
        │
        ├── /reject → TunerPipeline.approve_tier3(id, False)
        │   └── status=REJECTED, 사유 기록
        │
        └── 24시간 타임아웃 → 자동 거부
```

---

## 11. 기존 코드 연동

### 11.1 Bootstrap 연동

**파일:** `engine/bootstrap.py`

```python
# bootstrap() 함수 내, per-strategy 컴포넌트 등록 이후:
if settings.tuner.enabled:
    from engine.tuner import create_tuner

    tuner = await create_tuner(
        settings=settings.tuner,
        data_store=store,
        exchange_client=exchange,
        notifier=notifier,
        signal_generators=signal_generators,  # dict[str, SignalGenerator]
        risk_engines=risk_engines,            # dict[str, RiskEngine]
        regime_switch_managers=regime_managers,
    )
    app.register("tuner_pipeline", tuner)
```

스케줄러 등록:

```python
if settings.tuner.enabled:
    tuner: TunerPipeline = app.get("tuner_pipeline")

    # 주간 Tier 1 튜닝 (Mon 00:00 UTC = KST 09:00)
    app.scheduler.add_cron_job(
        tuner.run_scheduled_tuning,
        day_of_week="mon",
        hour=0,
        minute=0,
        job_id="tuner-weekly",
    )

    # 모니터링 체크 (매 시간)
    app.scheduler.add_interval_job(
        tuner.check_monitoring,
        seconds=3600,
        job_id="tuner-monitor",
    )
```

### 11.2 Factory 함수

**파일:** `engine/tuner/__init__.py`

```python
from __future__ import annotations

import os

from shared.protocols import DataStore, ExchangeClient, Notifier
from engine.strategy.signal import SignalGenerator
from engine.strategy.risk import RiskEngine
from engine.strategy.regime_switch import RegimeSwitchManager
from engine.tuner.config import TunerSettings
from engine.tuner.pipeline import TunerPipeline


async def create_tuner(
    settings: TunerSettings,
    data_store: DataStore,
    exchange_client: ExchangeClient,
    notifier: Notifier | None,
    signal_generators: dict[str, SignalGenerator],
    risk_engines: dict[str, RiskEngine],
    regime_switch_managers: dict[str, RegimeSwitchManager],
) -> TunerPipeline:
    """
    AI Tuner 파이프라인 팩토리.

    1. LLM 클라이언트 생성 (환경변수에서 API 키 로드)
    2. ProviderRouter 구성 (Circuit Breaker + CostTracker)
    3. TunerStore 생성
    4. 각 서브 모듈 생성 (Evaluator, Optimizer, Applier, RollbackMonitor)
    5. TunerPipeline 조립 및 반환
    """
    ...
```

### 11.3 EventBus 이벤트

**파일:** `shared/events.py`에 추가

```python
@dataclass(frozen=True)
class TuningAppliedEvent:
    """파라미터 튜닝이 적용되었을 때 발행."""
    tuning_id: str
    strategy_id: str
    changes: dict[str, dict[str, float]]  # {param: {old, new}}
    provider: str
    timestamp: float = field(default_factory=time)


@dataclass(frozen=True)
class TuningRolledBackEvent:
    """파라미터 튜닝이 롤백되었을 때 발행."""
    tuning_id: str
    strategy_id: str
    reason: str
    timestamp: float = field(default_factory=time)
```

### 11.4 DataStore 스키마 확장

`sqlite_store.py`의 `_SCHEMA` 문자열에 `tuning_history`와 `tuning_report` CREATE TABLE 추가. `postgres_store.py`에도 동일 (INTEGER → SERIAL, TEXT → TIMESTAMPTZ 등 방언 적용).

---

## 12. REST API

**파일:** `api/routes/tuning.py`

```python
from fastapi import APIRouter, Depends, Query

router = APIRouter(
    prefix="/tuning",
    tags=["tuning"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/history")
async def get_tuning_history(
    strategy_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """튜닝 이력 목록 조회."""
    ...


@router.get("/history/{tuning_id}")
async def get_tuning_detail(tuning_id: str) -> dict:
    """특정 튜닝 세션 상세 조회 (변경 내역 + 진단 + 검증 결과)."""
    ...


@router.post("/rollback/{tuning_id}")
async def manual_rollback(tuning_id: str) -> dict:
    """수동 롤백 실행."""
    ...


@router.get("/status")
async def get_tuner_status() -> dict:
    """
    반환:
    {
        "state": "idle|evaluating|...",
        "active_monitoring": [...tuning_ids...],
        "consecutive_rollbacks": 0,
        "last_tuning": {...}
    }
    """
    ...


@router.get("/provider-status")
async def get_provider_status() -> dict:
    """
    반환:
    {
        "claude": {"state": "closed", "failures": 0, "cost_usd": 0.05},
        "openai": {"state": "open", "failures": 3, "cost_usd": 0.00},
        "budget": {"used_usd": 0.05, "limit_usd": 5.0, "warning": false}
    }
    """
    ...


@router.post("/trigger/{strategy_id}")
async def trigger_tuning(
    strategy_id: str,
    tier: str = "tier_1",
) -> dict:
    """수동 튜닝 트리거 (디버깅용)."""
    ...


@router.post("/approve/{tuning_id}")
async def approve_tier3_change(
    tuning_id: str,
    approved: bool = True,
) -> dict:
    """Tier 3 변경 승인/거부."""
    ...
```

---

## 13. 테스트 전략

### 13.1 단위 테스트

| 파일 | 대상 | 접근법 |
|------|------|--------|
| `test_enums.py` | Enum 값 검증 | 순수 단위, I/O 없음 |
| `test_config.py` | TunerSettings 유효성, 환경변수 로드 | pydantic 검증 |
| `test_guardrails.py` | 클램핑, Tier 2 방향 검사, 가중치 정규화 | 순수 단위, 경계값 테스트 |
| `test_degraded.py` | 규칙 기반 진단/선택/승인 | parametrize로 엣지 케이스 |
| `test_provider_router.py` | CB 상태 전환, fallback 체인, 비용 추적 | Mock LLMClient |
| `test_llm_client.py` | 요청/응답 형식, 에러 핸들링 | httpx mock (respx) |
| `test_prompts.py` | 템플릿 렌더링, JSON 파싱, 비정상 응답 처리 | 문자열 검증 |
| `test_evaluator.py` | 지표 계산, LLM 호출 분기, 스킵 조건 | Mock DataStore + ProviderRouter |
| `test_optimizer.py` | Optuna 통합, 탐색 공간, 후보 순위 | Mock 백테스트, n_trials=3 |
| `test_applier.py` | SignalGenerator 속성 변경, 이력 저장, 롤백 | Mock SignalGenerator + TunerStore |
| `test_rollback.py` | MDD 비교, 연속 롤백 카운트, suspend | Mock PnL 데이터 |
| `test_pipeline.py` | 전체 오케스트레이션, 스킵 조건, 에러 경로 | Mock 전체 서브 모듈 |
| `test_store.py` | tuning 테이블 CRUD | In-memory SQLite |

### 13.2 통합 테스트

**파일:** `engine/tests/integration/test_tuning_cycle.py`

```
전체 파이프라인 테스트:
1. In-memory SQLite에 가짜 주문/포지션/시그널 삽입
2. Fake LLMClient (결정론적 JSON 반환)
3. Tiny Optuna study (n_trials=3) + 실제 BacktestEngine (합성 데이터)
4. 검증: evaluate → optimize → apply → monitoring → confirm/rollback
```

### 13.3 테스트 패턴

- `asyncio_mode = "auto"` (기존 관행: `@pytest.mark.asyncio` 불필요)
- LLM 클라이언트는 결정론적 JSON 응답으로 mock
- Optuna 테스트는 속도를 위해 `n_trials=3~5`
- CircuitBreaker 테스트는 `engine/tests/unit/test_circuit_breaker.py` 패턴 참조
- `SqliteDataStore(":memory:")` 사용 (기존 테스트 패턴)

---

## 14. 구현 순서

### Phase 1: 기반 인프라 + Evaluator (1~2주)

1. `engine/tuner/enums.py` — Enum 정의
2. `engine/tuner/models.py` — 데이터 모델
3. `engine/tuner/config.py` — 설정 클래스 + 파라미터 범위
4. `engine/tuner/store.py` — DB 접근 레이어
5. DB 스키마 확장: `sqlite_store.py`, `postgres_store.py`에 테이블 추가
6. `engine/tuner/llm_client.py` — Claude/OpenAI 클라이언트
7. `engine/tuner/provider_router.py` — 라우터 + CB + 비용 추적
8. `engine/tuner/prompts.py` — 프롬프트 템플릿
9. `engine/tuner/degraded.py` — 규칙 기반 fallback
10. `engine/tuner/evaluator.py` — 성과 평가 + LLM 진단
11. `engine/config/settings.py` — TunerSettings 추가
12. Phase 1 단위 테스트

**검증:** LLM 프로바이더 fallback 동작 (Claude → OpenAI → Degraded)

### Phase 2: Optimizer + Guardrails (2~3주)

1. `engine/tuner/guardrails.py` — 안전 규칙
2. `engine/tuner/optimizer.py` — Optuna + LLM 선택
3. `pyproject.toml`에 `optuna` 의존성 추가
4. Phase 2 단위 테스트

**검증:** Degraded Mode에서도 합리적 파라미터 선택되는지 비교

### Phase 3: Applier + Rollback + Pipeline (1~2주)

1. `engine/tuner/applier.py` — hot-reload + 이력
2. `engine/tuner/rollback.py` — 모니터링 + 자동 롤백
3. `engine/tuner/pipeline.py` — 오케스트레이션
4. `engine/tuner/__init__.py` — create_tuner() 팩토리
5. `engine/bootstrap.py` — 튜너 등록 + 스케줄러
6. `shared/events.py` — 튜닝 이벤트 추가
7. 통합 테스트

**검증:** 롤백 시 이전 파라미터 완전 복원 확인

### Phase 4: API + 대시보드 (1~2주)

1. `api/routes/tuning.py` — REST 엔드포인트 7종
2. 텔레그램 Tier 3 승인 플로우
3. 대시보드 튜닝 이력 시각화 (별도 설계)
4. E2E 테스트

---

## 15. 의존성

### 신규 Python 패키지

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `optuna` | >=3.6 | 베이지안 최적화 |

### 기존 패키지 (추가 불필요)

- `httpx` — LLM API 호출 (TelegramNotifier에서 이미 사용)
- `pydantic-settings` — 설정 관리
- `aiosqlite` / `asyncpg` — DB 접근
