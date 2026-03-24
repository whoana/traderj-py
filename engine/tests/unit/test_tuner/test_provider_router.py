"""Tests for engine.tuner.provider_router."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from engine.execution.circuit_breaker import CircuitBreaker
from engine.tuner.models import LLMResponse
from engine.tuner.provider_router import CostTracker, ProviderRouter


def _mock_client(name: str, response: LLMResponse | None = None, error: Exception | None = None) -> AsyncMock:
    client = AsyncMock()
    client.provider_name = name
    client.model_name = f"{name}-model"
    if error:
        client.complete = AsyncMock(side_effect=error)
    else:
        resp = response or LLMResponse(
            text='{"result": "ok"}',
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            provider=name,
            model=f"{name}-model",
        )
        client.complete = AsyncMock(return_value=resp)
    return client


class TestCostTracker:
    def test_record_and_check(self):
        ct = CostTracker(monthly_budget_usd=1.0)
        assert not ct.is_budget_exceeded()
        ct.record_cost(0.5, "claude")
        assert not ct.is_budget_exceeded()
        assert not ct.is_budget_warning()  # 0.5/1.0 = 50%, warning at 80%
        ct.record_cost(0.4, "claude")
        assert ct.is_budget_warning()  # 0.9/1.0 = 90%
        ct.record_cost(0.2, "openai")
        assert ct.is_budget_exceeded()

    def test_monthly_usage(self):
        ct = CostTracker(monthly_budget_usd=10.0)
        ct.record_cost(0.05, "claude")
        ct.record_cost(0.03, "openai")
        usage = ct.get_monthly_usage()
        assert usage["claude"] == pytest.approx(0.05)
        assert usage["openai"] == pytest.approx(0.03)


class TestProviderRouter:
    async def test_primary_success(self):
        client = _mock_client("claude")
        cb = CircuitBreaker(failure_threshold=3)
        ct = CostTracker(monthly_budget_usd=10.0)
        router = ProviderRouter([client], {"claude": cb}, ct)

        result = await router.complete("sys", "user")
        assert result is not None
        assert result.provider == "claude"
        assert router.active_provider == "claude"
        assert not router.is_degraded

    async def test_fallback_on_failure(self):
        primary = _mock_client("claude", error=RuntimeError("API down"))
        fallback = _mock_client("openai")
        cbs = {
            "claude": CircuitBreaker(failure_threshold=3),
            "openai": CircuitBreaker(failure_threshold=3),
        }
        ct = CostTracker(monthly_budget_usd=10.0)
        router = ProviderRouter([primary, fallback], cbs, ct)

        result = await router.complete("sys", "user")
        assert result is not None
        assert result.provider == "openai"
        assert router.active_provider == "openai"

    async def test_degraded_when_all_fail(self):
        primary = _mock_client("claude", error=RuntimeError("down"))
        fallback = _mock_client("openai", error=RuntimeError("down"))
        cbs = {
            "claude": CircuitBreaker(failure_threshold=3),
            "openai": CircuitBreaker(failure_threshold=3),
        }
        ct = CostTracker(monthly_budget_usd=10.0)
        router = ProviderRouter([primary, fallback], cbs, ct, degraded_enabled=True)

        result = await router.complete("sys", "user")
        assert result is None
        assert router.is_degraded

    async def test_error_when_degraded_disabled(self):
        primary = _mock_client("claude", error=RuntimeError("down"))
        cbs = {"claude": CircuitBreaker(failure_threshold=3)}
        ct = CostTracker(monthly_budget_usd=10.0)
        router = ProviderRouter([primary], cbs, ct, degraded_enabled=False)

        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            await router.complete("sys", "user")

    async def test_skip_open_circuit_breaker(self):
        primary = _mock_client("claude")
        fallback = _mock_client("openai")
        cb_claude = CircuitBreaker(failure_threshold=1)
        cb_claude.record_failure()  # trips to OPEN
        cbs = {"claude": cb_claude, "openai": CircuitBreaker(failure_threshold=3)}
        ct = CostTracker(monthly_budget_usd=10.0)
        router = ProviderRouter([primary, fallback], cbs, ct)

        result = await router.complete("sys", "user")
        assert result is not None
        assert result.provider == "openai"
        primary.complete.assert_not_called()

    async def test_budget_exceeded_goes_degraded(self):
        client = _mock_client("claude")
        cbs = {"claude": CircuitBreaker()}
        ct = CostTracker(monthly_budget_usd=0.001)
        ct.record_cost(0.01, "claude")  # exceed
        router = ProviderRouter([client], cbs, ct, degraded_enabled=True)

        result = await router.complete("sys", "user")
        assert result is None
        assert router.is_degraded

    def test_get_provider_status(self):
        client = _mock_client("claude")
        cb = CircuitBreaker(failure_threshold=3)
        ct = CostTracker(monthly_budget_usd=5.0)
        ct.record_cost(0.05, "claude")
        router = ProviderRouter([client], {"claude": cb}, ct)

        status = router.get_provider_status()
        assert "claude" in status
        assert status["claude"]["state"] == "closed"
        assert status["budget"]["used_usd"] == pytest.approx(0.05)
        assert status["budget"]["limit_usd"] == 5.0
