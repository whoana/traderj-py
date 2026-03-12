"""WebSocket endpoint and manager tests."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from api.deps import app_state
from api.main import create_app
from api.ws.manager import ConnectionManager, VALID_CHANNELS


# ── FakeDataStore (minimal for WS tests) ────────────────────────


class FakeDataStore:
    async def get_bot_state(self, sid):
        return None

    async def get_pending_commands(self):
        return []

    async def close(self):
        pass


# ── Unit: ConnectionManager ─────────────────────────────────────


class FakeWebSocket:
    """Minimal WebSocket mock for unit testing the manager."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self, code=1000, reason="") -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_manager_connect_disconnect():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)
    assert mgr.connection_count == 1
    await mgr.disconnect(ws)
    assert mgr.connection_count == 0


@pytest.mark.asyncio
async def test_manager_subscribe():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)
    subscribed = await mgr.subscribe(ws, ["ticker", "orders", "invalid_channel"])
    assert "ticker" in subscribed
    assert "orders" in subscribed
    assert "invalid_channel" not in subscribed


@pytest.mark.asyncio
async def test_manager_unsubscribe():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)
    await mgr.subscribe(ws, ["ticker", "orders"])
    removed = await mgr.unsubscribe(ws, ["ticker"])
    assert removed == ["ticker"]


@pytest.mark.asyncio
async def test_manager_broadcast():
    mgr = ConnectionManager()
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()
    await mgr.connect(ws1)
    await mgr.connect(ws2)
    await mgr.subscribe(ws1, ["ticker"])
    # ws2 not subscribed to ticker

    await mgr.broadcast("ticker", {"price": 80000000})

    assert len(ws1.sent) == 1
    msg = json.loads(ws1.sent[0])
    assert msg["type"] == "data"
    assert msg["channel"] == "ticker"
    assert msg["payload"]["price"] == 80000000
    assert len(ws2.sent) == 0


@pytest.mark.asyncio
async def test_manager_handle_subscribe_message():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)

    await mgr.handle_message(ws, json.dumps({
        "type": "subscribe", "channels": ["ticker", "alerts"]
    }))

    assert len(ws.sent) == 1
    resp = json.loads(ws.sent[0])
    assert resp["type"] == "subscribed"
    assert set(resp["channels"]) == {"ticker", "alerts"}


@pytest.mark.asyncio
async def test_manager_handle_pong():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)
    await mgr.handle_message(ws, json.dumps({"type": "pong"}))
    # No error, pong timestamp updated


@pytest.mark.asyncio
async def test_manager_handle_invalid_json():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)
    await mgr.handle_message(ws, "not json{")
    resp = json.loads(ws.sent[0])
    assert resp["type"] == "error"
    assert resp["code"] == "invalid_json"


@pytest.mark.asyncio
async def test_manager_handle_unknown_type():
    mgr = ConnectionManager()
    ws = FakeWebSocket()
    await mgr.connect(ws)
    await mgr.handle_message(ws, json.dumps({"type": "unknown_cmd"}))
    resp = json.loads(ws.sent[0])
    assert resp["type"] == "error"
    assert resp["code"] == "unknown_type"


@pytest.mark.asyncio
async def test_valid_channels():
    assert VALID_CHANNELS == {"ticker", "bot_status", "orders", "positions", "signals", "alerts"}


# ── Integration: WebSocket endpoint via TestClient ───────────────


def test_ws_auth_rejected():
    """Connection without API key should be rejected."""
    app_state.set_data_store(FakeDataStore())
    app_state.set_engine_client(None)
    app = create_app()
    client = TestClient(app)
    # No api_key → should close with 4001
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/v1/stream"):
            pass
    app_state.data_store = None


def test_ws_subscribe_flow():
    """Full subscribe → broadcast → receive flow."""
    app_state.set_data_store(FakeDataStore())
    app_state.set_engine_client(None)
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/ws/v1/stream?api_key=dev-api-key") as ws:
        # Subscribe
        ws.send_text(json.dumps({"type": "subscribe", "channels": ["ticker"]}))
        resp = json.loads(ws.receive_text())
        assert resp["type"] == "subscribed"
        assert "ticker" in resp["channels"]

        # Pong
        ws.send_text(json.dumps({"type": "pong"}))

    app_state.data_store = None
