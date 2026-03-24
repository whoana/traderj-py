"""AI Tuner module — automated strategy parameter optimization.

Phase 1: Evaluator + LLM integration + provider routing.
Phase 2: Optimizer + Guardrails.
Phase 3: Applier + Rollback + Pipeline + bootstrap integration.
"""

from __future__ import annotations

import os

from engine.execution.circuit_breaker import CircuitBreaker
from engine.tuner.applier import ParameterApplier
from engine.tuner.config import TunerSettings
from engine.tuner.degraded import DegradedFallback
from engine.tuner.evaluator import StrategyEvaluator
from engine.tuner.guardrails import Guardrails
from engine.tuner.llm_client import ClaudeLLMClient, LLMClient, OpenAILLMClient
from engine.tuner.optimizer import HybridOptimizer
from engine.tuner.pipeline import TunerPipeline
from engine.tuner.provider_router import CostTracker, ProviderRouter
from engine.tuner.rollback import RollbackMonitor
from engine.tuner.store import TunerStore


def _build_provider_router(settings: TunerSettings) -> tuple[ProviderRouter, list[LLMClient]]:
    """Build LLM providers and router (sync — clients started later)."""
    providers: list[LLMClient] = []
    circuit_breakers: dict[str, CircuitBreaker] = {}

    llm = settings.llm
    recovery_sec = llm.cb_recovery_timeout_min * 60.0

    if llm.llm_primary == "claude" and os.environ.get("ANTHROPIC_API_KEY"):
        providers.append(ClaudeLLMClient(model=llm.claude_model, timeout=llm.claude_timeout))
        circuit_breakers["claude"] = CircuitBreaker(
            failure_threshold=llm.cb_failure_threshold,
            recovery_seconds=recovery_sec,
        )

    if llm.llm_primary == "openai" and os.environ.get("OPENAI_API_KEY"):
        providers.append(OpenAILLMClient(model=llm.openai_model, timeout=llm.openai_timeout))
        circuit_breakers["openai"] = CircuitBreaker(
            failure_threshold=llm.cb_failure_threshold,
            recovery_seconds=recovery_sec,
        )

    if llm.llm_fallback == "openai" and "openai" not in circuit_breakers and os.environ.get("OPENAI_API_KEY"):
        providers.append(OpenAILLMClient(model=llm.openai_model, timeout=llm.openai_timeout))
        circuit_breakers["openai"] = CircuitBreaker(
            failure_threshold=llm.cb_failure_threshold,
            recovery_seconds=recovery_sec,
        )

    if llm.llm_fallback == "claude" and "claude" not in circuit_breakers and os.environ.get("ANTHROPIC_API_KEY"):
        providers.append(ClaudeLLMClient(model=llm.claude_model, timeout=llm.claude_timeout))
        circuit_breakers["claude"] = CircuitBreaker(
            failure_threshold=llm.cb_failure_threshold,
            recovery_seconds=recovery_sec,
        )

    cost_tracker = CostTracker(
        monthly_budget_usd=llm.monthly_budget_usd,
        warning_pct=llm.budget_warning_pct,
    )

    router = ProviderRouter(
        providers=providers,
        circuit_breakers=circuit_breakers,
        cost_tracker=cost_tracker,
        degraded_enabled=llm.llm_degraded_enabled,
    )

    return router, providers


async def create_tuner_evaluator(
    settings: TunerSettings,
    data_store: object,
    notifier: object | None = None,
) -> StrategyEvaluator:
    """Create Phase 1 evaluator with LLM provider routing."""
    router, providers = _build_provider_router(settings)
    for p in providers:
        if hasattr(p, "start"):
            await p.start()

    tuner_store = TunerStore(data_store)
    degraded = DegradedFallback()

    return StrategyEvaluator(
        data_store=data_store,
        tuner_store=tuner_store,
        provider_router=router,
        degraded=degraded,
        notifier=notifier,
    )


async def create_tuner(
    settings: TunerSettings,
    data_store: object,
    notifier: object | None = None,
) -> TunerPipeline:
    """Create full TunerPipeline with all components.

    Returns a TunerPipeline ready for strategy registration and scheduling.
    Call pipeline.register_strategy() for each active strategy.
    """
    router, providers = _build_provider_router(settings)
    for p in providers:
        if hasattr(p, "start"):
            await p.start()

    tuner_store = TunerStore(data_store)
    degraded = DegradedFallback()
    guardrails = Guardrails(settings.guardrails, tuner_store)

    evaluator = StrategyEvaluator(
        data_store=data_store,
        tuner_store=tuner_store,
        provider_router=router,
        degraded=degraded,
        notifier=notifier,
    )

    optimizer = HybridOptimizer(
        provider_router=router,
        degraded=degraded,
        config=settings.guardrails,
    )

    applier = ParameterApplier(
        tuner_store=tuner_store,
        guardrails=guardrails,
        notifier=notifier,
        monitoring_hours=settings.guardrails.monitoring_hours,
    )

    rollback_monitor = RollbackMonitor(
        data_store=data_store,
        tuner_store=tuner_store,
        applier=applier,
        notifier=notifier,
        config=settings.guardrails,
    )

    return TunerPipeline(
        evaluator=evaluator,
        optimizer=optimizer,
        applier=applier,
        rollback_monitor=rollback_monitor,
        tuner_store=tuner_store,
        notifier=notifier,
        config=settings,
    )
