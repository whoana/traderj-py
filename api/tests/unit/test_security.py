"""Tests for security middleware and Prometheus metrics."""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from api.middleware.security import SensitiveDataFilter

# ── SensitiveDataFilter tests ────────────────────────────────────────


class TestSensitiveDataFilter:
    def setup_method(self):
        self.filter = SensitiveDataFilter()

    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        return record

    def test_redacts_api_key(self):
        record = self._make_record("User sent api_key=abc123 in request")
        self.filter.filter(record)
        assert "abc123" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_redacts_token(self):
        record = self._make_record("Authorization: Bearer token_value_123")
        self.filter.filter(record)
        assert "[REDACTED]" in record.msg

    def test_redacts_password(self):
        record = self._make_record("password=mysecret&user=admin")
        self.filter.filter(record)
        assert "[REDACTED]" in record.msg

    def test_passes_safe_messages(self):
        record = self._make_record("GET /api/v1/health returned 200")
        self.filter.filter(record)
        assert record.msg == "GET /api/v1/health returned 200"


# ── Security headers tests ───────────────────────────────────────────

@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_security_headers(client: AsyncClient):
    resp = await client.get(
        "/api/v1/health",
        headers={"X-API-Key": "dev-api-key"},
    )
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert resp.headers.get("Cache-Control") == "no-store"


async def test_cors_env_origins(client: AsyncClient, monkeypatch):
    """CORS origins come from CORS_ORIGINS env var."""
    # Default includes localhost:3000
    resp = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200


async def test_metrics_endpoint(client: AsyncClient):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "traderj_http_requests_total" in resp.text


async def test_docs_available_in_dev(client: AsyncClient):
    """Swagger docs available when not in production."""
    resp = await client.get("/api/v1/docs")
    assert resp.status_code == 200
