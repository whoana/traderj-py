"""LLM provider router with circuit breakers and cost tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import monotonic

from engine.execution.circuit_breaker import CBState, CircuitBreaker
from engine.tuner.llm_client import LLMClient
from engine.tuner.models import LLMResponse

logger = logging.getLogger(__name__)


class CostTracker:
    """Tracks monthly LLM API costs."""

    def __init__(self, monthly_budget_usd: float, warning_pct: float = 0.8) -> None:
        self._budget = monthly_budget_usd
        self._warning_pct = warning_pct
        self._costs: dict[str, float] = {}  # provider -> total_cost
        self._reset_month: int = datetime.now(tz=timezone.utc).month

    def record_cost(self, cost_usd: float, provider: str) -> None:
        self._maybe_reset()
        self._costs[provider] = self._costs.get(provider, 0.0) + cost_usd

    def is_budget_exceeded(self) -> bool:
        self._maybe_reset()
        return self.total_used >= self._budget

    def is_budget_warning(self) -> bool:
        self._maybe_reset()
        return self.total_used >= self._budget * self._warning_pct

    @property
    def total_used(self) -> float:
        return sum(self._costs.values())

    def get_monthly_usage(self) -> dict[str, float]:
        self._maybe_reset()
        return dict(self._costs)

    def _maybe_reset(self) -> None:
        current_month = datetime.now(tz=timezone.utc).month
        if current_month != self._reset_month:
            self._costs.clear()
            self._reset_month = current_month
            logger.info("CostTracker: monthly reset (new month %d)", current_month)


class ProviderRouter:
    """Routes LLM calls through the provider chain with circuit breakers."""

    def __init__(
        self,
        providers: list[LLMClient],
        circuit_breakers: dict[str, CircuitBreaker],
        cost_tracker: CostTracker,
        degraded_enabled: bool = True,
    ) -> None:
        self._providers = providers
        self._circuit_breakers = circuit_breakers
        self._cost_tracker = cost_tracker
        self._degraded_enabled = degraded_enabled
        self._active_provider: str = providers[0].provider_name if providers else "degraded"

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> LLMResponse | None:
        """Try providers in priority order. Returns None if all fail and degraded is enabled."""
        if self._cost_tracker.is_budget_exceeded():
            logger.warning("LLM budget exceeded ($%.2f), entering degraded mode", self._cost_tracker.total_used)
            self._active_provider = "degraded"
            return None

        for provider in self._providers:
            name = provider.provider_name
            cb = self._circuit_breakers.get(name)
            if cb and not cb.allow_request():
                logger.debug("Provider %s circuit breaker OPEN, skipping", name)
                continue

            try:
                response = await provider.complete(system_prompt, user_prompt, max_tokens)
                if cb:
                    cb.record_success()
                self._cost_tracker.record_cost(response.cost_usd, name)
                self._active_provider = name

                if self._cost_tracker.is_budget_warning():
                    logger.warning(
                        "LLM budget warning: $%.2f / $%.2f",
                        self._cost_tracker.total_used,
                        self._cost_tracker._budget,
                    )

                return response

            except Exception:
                logger.exception("LLM provider %s failed", name)
                if cb:
                    cb.record_failure()

        # All providers failed
        self._active_provider = "degraded"
        if self._degraded_enabled:
            logger.warning("All LLM providers failed, entering degraded mode")
            return None

        msg = "All LLM providers failed and degraded mode is disabled"
        raise RuntimeError(msg)

    @property
    def active_provider(self) -> str:
        return self._active_provider

    @property
    def is_degraded(self) -> bool:
        return self._active_provider == "degraded"

    def get_provider_status(self) -> dict[str, dict]:
        """Return status of all providers and budget."""
        status: dict[str, dict] = {}
        usage = self._cost_tracker.get_monthly_usage()

        for provider in self._providers:
            name = provider.provider_name
            cb = self._circuit_breakers.get(name)
            status[name] = {
                "state": cb.state.value if cb else "unknown",
                "failures": cb.consecutive_failures if cb else 0,
                "cost_usd": usage.get(name, 0.0),
            }

        status["budget"] = {
            "used_usd": self._cost_tracker.total_used,
            "limit_usd": self._cost_tracker._budget,
            "warning": self._cost_tracker.is_budget_warning(),
            "exceeded": self._cost_tracker.is_budget_exceeded(),
        }

        return status
