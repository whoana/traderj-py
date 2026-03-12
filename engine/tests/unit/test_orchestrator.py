"""Unit tests for AppOrchestrator."""

from __future__ import annotations

import asyncio

import pytest

from engine.app import AppOrchestrator
from engine.config.settings import AppSettings


class FakeDataStore:
    """Minimal stub implementing connect/disconnect."""

    def __init__(self) -> None:
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False


class FakeStartable:
    """Component with start/stop lifecycle."""

    def __init__(self) -> None:
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False


class TestAppOrchestrator:
    async def test_start_and_stop(self) -> None:
        app = AppOrchestrator()
        ds = FakeDataStore()
        app.register("datastore", ds)

        await app.start()
        assert app.is_started
        assert ds.connected
        assert app.event_bus.is_running

        await app.stop()
        assert not app.is_started
        assert not ds.connected
        assert not app.event_bus.is_running

    async def test_register_and_get(self) -> None:
        app = AppOrchestrator()
        comp = FakeStartable()
        app.register("my_comp", comp)

        assert app.get("my_comp") is comp

    async def test_get_unknown_raises(self) -> None:
        app = AppOrchestrator()
        with pytest.raises(KeyError, match="Component not registered"):
            app.get("nonexistent")

    async def test_custom_component_lifecycle(self) -> None:
        app = AppOrchestrator()
        comp = FakeStartable()
        app.register("custom", comp)

        await app.start()
        assert comp.started

        await app.stop()
        assert not comp.started

    async def test_start_idempotent(self) -> None:
        app = AppOrchestrator()
        await app.start()
        await app.start()  # Should not raise
        assert app.is_started
        await app.stop()

    async def test_stop_idempotent(self) -> None:
        app = AppOrchestrator()
        await app.start()
        await app.stop()
        await app.stop()  # Should not raise
        assert not app.is_started

    async def test_settings_default(self) -> None:
        app = AppOrchestrator()
        assert app.settings.env == "development"
        assert app.settings.trading.mode == "paper"

    async def test_settings_custom(self) -> None:
        settings = AppSettings(env="production")
        app = AppOrchestrator(settings=settings)
        assert app.settings.env == "production"

    async def test_components_dict(self) -> None:
        app = AppOrchestrator()
        ds = FakeDataStore()
        app.register("datastore", ds)
        app.register("other", FakeStartable())

        comps = app.components
        assert "datastore" in comps
        assert "other" in comps
        assert len(comps) == 2

    async def test_run_with_shutdown_event(self) -> None:
        """run() should start, then stop when shutdown event is set."""
        app = AppOrchestrator()
        ds = FakeDataStore()
        app.register("datastore", ds)

        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            app._shutdown_event.set()

        task = asyncio.create_task(trigger_shutdown())
        await app.run()
        await task

        assert not app.is_started
        assert not ds.connected
