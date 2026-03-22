"""IPC integration test — Engine↔API Unix Domain Socket communication.

Tests:
1. IPCServer starts and accepts connections
2. Event broadcast reaches connected clients
3. Command from client is saved to DB
4. Client disconnect is handled gracefully
"""

from __future__ import annotations

import asyncio
import json

import pytest

from engine.data.sqlite_store import SqliteDataStore
from engine.loop.event_bus import EventBus
from engine.loop.ipc_server import IPCServer


@pytest.fixture
async def store():
    s = SqliteDataStore(":memory:")
    await s.connect()
    yield s
    await s.disconnect()


@pytest.fixture
async def bus():
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
def socket_path():
    import os
    path = f"/tmp/traderj_test_{os.getpid()}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
async def ipc_server(store, bus, socket_path):
    server = IPCServer(event_bus=bus, data_store=store, socket_path=socket_path)
    await server.start()
    yield server
    await server.stop()


async def _connect_client(socket_path: str):
    """Connect a test client to the IPC server."""
    reader, writer = await asyncio.open_unix_connection(socket_path)
    return reader, writer


async def test_server_starts_and_accepts_connection(ipc_server, socket_path):
    reader, writer = await _connect_client(socket_path)
    # Give server time to register client
    await asyncio.sleep(0.05)
    assert len(ipc_server._clients) == 1
    writer.close()
    await writer.wait_closed()


async def test_event_broadcast(ipc_server, socket_path):
    reader, writer = await _connect_client(socket_path)
    await asyncio.sleep(0.05)

    # Broadcast an event
    await ipc_server.broadcast_event("MarketTickEvent", {
        "symbol": "BTC/KRW",
        "price": "90000000",
        "volume": "100",
    })

    # Read the broadcasted message
    line = await asyncio.wait_for(reader.readline(), timeout=2.0)
    msg = json.loads(line.decode().strip())

    assert msg["event_type"] == "MarketTickEvent"
    assert msg["data"]["symbol"] == "BTC/KRW"
    assert msg["data"]["price"] == "90000000"

    writer.close()
    await writer.wait_closed()


async def test_multiple_clients_receive_broadcast(ipc_server, socket_path):
    readers_writers = [await _connect_client(socket_path) for _ in range(3)]
    await asyncio.sleep(0.05)
    assert len(ipc_server._clients) == 3

    await ipc_server.broadcast_event("BotStateChangeEvent", {
        "strategy_id": "strat-1",
        "state": "running",
    })

    for reader, _writer in readers_writers:
        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        msg = json.loads(line.decode().strip())
        assert msg["event_type"] == "BotStateChangeEvent"

    for _, writer in readers_writers:
        writer.close()
        await writer.wait_closed()


async def test_client_command_saved_to_db(ipc_server, store, socket_path):
    reader, writer = await _connect_client(socket_path)
    await asyncio.sleep(0.05)

    # Send a command from "API" to "Engine"
    cmd = json.dumps({
        "type": "command",
        "action": "start",
        "strategy_id": "strat-1",
        "params": {"mode": "paper"},
    }) + "\n"
    writer.write(cmd.encode())
    await writer.drain()

    # Give server time to process
    await asyncio.sleep(0.1)

    # Verify command was saved to DB
    pending = await store.get_pending_commands("strat-1")
    assert len(pending) == 1
    assert pending[0].command == "start"
    assert pending[0].strategy_id == "strat-1"
    assert pending[0].params == {"mode": "paper"}

    writer.close()
    await writer.wait_closed()


async def test_client_disconnect_cleanup(ipc_server, socket_path):
    reader, writer = await _connect_client(socket_path)
    await asyncio.sleep(0.05)
    assert len(ipc_server._clients) == 1

    writer.close()
    await writer.wait_closed()
    await asyncio.sleep(0.1)

    # Broadcast to trigger dead client cleanup
    await ipc_server.broadcast_event("test", {})
    await asyncio.sleep(0.05)
    assert len(ipc_server._clients) == 0
