"""Tests for api/routes/tuning.py — tuning REST API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.deps import app_state
from api.main import create_app
from engine.tuner.enums import LLMProviderName, TierLevel, TunerState, TuningStatus
from engine.tuner.models import (
    ApplyResult,
    EvalMetrics,
    ParameterChange,
    TuningHistoryRecord,
    TuningSessionResult,
)

API_KEY = "dev-api-key"
HEADERS = {"X-API-Key": API_KEY}


def _mock_record(tuning_id: str = "tune-001", status: TuningStatus = TuningStatus.MONITORING) -> TuningHistoryRecord:
    return TuningHistoryRecord(
        tuning_id=tuning_id,
        created_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        strategy_id="STR-001",
        changes=[
            ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20),
        ],
        eval_metrics=EvalMetrics(
            strategy_id="STR-001",
            eval_window="2026-03-13~2026-03-20",
            regime="RANGING_LOW_VOL",
            total_trades=10,
            win_rate=0.40,
            profit_factor=1.2,
            max_drawdown=0.03,
            avg_r_multiple=0.8,
            signal_accuracy=0.35,
            avg_holding_hours=6.0,
            total_return_pct=0.01,
            sharpe_ratio=0.4,
        ),
        validation_pf=1.5,
        validation_mdd=0.02,
        llm_provider=LLMProviderName.DEGRADED,
        llm_model=None,
        llm_diagnosis=None,
        llm_confidence=None,
        reason="test",
        status=status,
    )


def _setup_mock_pipeline():
    """Create mock TunerPipeline and inject into app_state."""
    pipeline = MagicMock()

    # Mock store
    store = MagicMock()
    store.get_tuning_history = AsyncMock(return_value=[_mock_record()])
    store.get_latest_tuning = AsyncMock(return_value=_mock_record())
    store.get_monitoring_sessions = AsyncMock(return_value=[_mock_record()])
    pipeline._store = store

    # Mock evaluator with router
    router = MagicMock()
    router.get_provider_status = MagicMock(return_value={
        "claude": {"state": "closed", "failures": 0},
        "budget": {"used_usd": 0.05, "limit_usd": 5.0},
    })
    evaluator = MagicMock()
    evaluator._router = router
    pipeline._evaluator = evaluator

    # Mock rollback monitor
    rollback = MagicMock()
    rollback.consecutive_rollback_count = 0
    pipeline._rollback = rollback

    # Mock state
    type(pipeline).state = PropertyMock(return_value=TunerState.IDLE)

    # Mock strategies
    pipeline._strategies = {"STR-001": {"signal_generator": MagicMock()}}

    # Mock methods
    pipeline.manual_rollback = AsyncMock(return_value=True)
    pipeline.run_tuning_session = AsyncMock(return_value=TuningSessionResult(
        tuning_id="tune-002",
        strategy_id="STR-001",
        tier=TierLevel.TIER_1,
        status=TuningStatus.MONITORING,
        changes=[ParameterChange("buy_threshold", TierLevel.TIER_1, 0.10, 0.12, 0.20)],
        eval_metrics=None,
        reason="tuning_applied",
    ))
    pipeline.approve_tier3 = AsyncMock(return_value=True)

    app_state.tuner_pipeline = pipeline
    return pipeline


@pytest.fixture
def _inject_pipeline():
    """Inject mock pipeline before test, clean up after."""
    pipeline = _setup_mock_pipeline()
    yield pipeline
    app_state.tuner_pipeline = None


class TestTuningHistory:
    async def test_get_history(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/tuning/history", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tuning_id"] == "tune-001"

    async def test_get_detail(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/tuning/history/tune-001", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["tuning_id"] == "tune-001"

    async def test_get_detail_not_found(self, _inject_pipeline):
        _inject_pipeline._store.get_tuning_history = AsyncMock(return_value=[])
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/tuning/history/nonexistent", headers=HEADERS)
        assert resp.status_code == 404


class TestTuningRollback:
    async def test_manual_rollback(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/tuning/rollback/tune-001", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "rolled_back"


class TestTuningStatus:
    async def test_get_status(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/tuning/status", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "idle"
        assert "STR-001" in data["registered_strategies"]


class TestProviderStatus:
    async def test_get_provider_status(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/tuning/provider-status", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "claude" in data
        assert "budget" in data


class TestTuningTrigger:
    async def test_trigger_tuning(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/tuning/trigger/STR-001",
                headers=HEADERS,
                json={"tier": "tier_1"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tuning_id"] == "tune-002"
        assert data["status"] == "monitoring"

    async def test_trigger_unknown_strategy(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/tuning/trigger/UNKNOWN",
                headers=HEADERS,
                json={"tier": "tier_1"},
            )
        assert resp.status_code == 404


class TestTuningApproval:
    async def test_approve_tier3(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/tuning/approve/tune-001",
                headers=HEADERS,
                json={"approved": True},
            )
        assert resp.status_code == 200
        assert resp.json()["action"] == "approved"


class TestAuthRequired:
    async def test_no_api_key_returns_401(self, _inject_pipeline):
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/tuning/status")
        assert resp.status_code == 401
