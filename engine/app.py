"""AppOrchestrator — DI container and lifecycle manager for the engine.

Responsibilities:
  - Wire all components (DataStore, EventBus, Scheduler, etc.)
  - Manage startup/shutdown ordering
  - Handle SIGTERM/SIGINT for graceful shutdown
  - Expose a run() coroutine as the engine entry point
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from engine.config.settings import AppSettings
from engine.loop.event_bus import EventBus
from engine.loop.scheduler import Scheduler

logger = logging.getLogger(__name__)


class AppOrchestrator:
    """Central DI container and lifecycle manager."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or AppSettings()
        self.event_bus = EventBus()
        self.scheduler = Scheduler()

        # Component registry — filled during setup
        self._components: dict[str, Any] = {}
        self._shutdown_event = asyncio.Event()
        self._started = False

    def register(self, name: str, component: Any) -> None:
        """Register a named component for DI lookup."""
        self._components[name] = component
        logger.debug("Registered component: %s", name)

    def get(self, name: str) -> Any:
        """Retrieve a registered component by name."""
        comp = self._components.get(name)
        if comp is None:
            raise KeyError(f"Component not registered: {name}")
        return comp

    async def start(self) -> None:
        """Start all components in dependency order.

        Order:
          1. DataStore (connect)
          2. EventBus (start processing)
          3. Scheduler (start jobs)
          4. Custom startables
        """
        if self._started:
            logger.warning("AppOrchestrator already started")
            return

        logger.info(
            "Starting AppOrchestrator (env=%s, mode=%s)",
            self.settings.env,
            self.settings.trading.mode,
        )

        # 1. DataStore
        datastore = self._components.get("datastore")
        if datastore is not None:
            await datastore.connect()
            logger.info("DataStore connected")

        # 2. EventBus
        await self.event_bus.start()

        # 3. Scheduler
        self.scheduler.start()

        # 4. Custom startable components
        for name, comp in self._components.items():
            if hasattr(comp, "start") and name != "datastore":
                await comp.start()
                logger.info("Started component: %s", name)

        self._started = True
        logger.info("AppOrchestrator started — all components up")

    async def stop(self) -> None:
        """Shut down all components in reverse order.

        Order:
          1. Scheduler (stop accepting new jobs)
          2. Custom stoppables
          3. EventBus (drain and stop)
          4. DataStore (disconnect)
        """
        if not self._started:
            return

        logger.info("Stopping AppOrchestrator...")

        # 1. Scheduler
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        # 2. Custom stoppable components (reverse registration order)
        for name in reversed(list(self._components)):
            comp = self._components[name]
            if hasattr(comp, "stop") and name != "datastore":
                try:
                    await comp.stop()
                    logger.info("Stopped component: %s", name)
                except Exception:
                    logger.exception("Error stopping component: %s", name)

        # 3. EventBus
        await self.event_bus.stop()

        # 4. DataStore
        datastore = self._components.get("datastore")
        if datastore is not None:
            await datastore.disconnect()
            logger.info("DataStore disconnected")

        self._started = False
        logger.info("AppOrchestrator stopped")

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Install SIGTERM/SIGINT handlers for graceful shutdown."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal, sig)
        logger.info("Signal handlers installed (SIGTERM, SIGINT)")

    def _handle_signal(self, sig: signal.Signals) -> None:
        logger.info("Received signal %s — initiating shutdown", sig.name)
        self._shutdown_event.set()

    async def run(self) -> None:
        """Main entry point — start, wait for shutdown signal, then stop."""
        loop = asyncio.get_running_loop()
        self.install_signal_handlers(loop)

        # Start Prometheus metrics HTTP server
        try:
            from engine.metrics import start_metrics_server

            start_metrics_server()
            logger.info("Prometheus metrics server started on port %s",
                        self.settings.prometheus_port if hasattr(self.settings, "prometheus_port") else 8001)
        except Exception:
            logger.warning("Failed to start Prometheus metrics server", exc_info=True)

        await self.start()

        # Block until shutdown signal
        await self._shutdown_event.wait()

        await self.stop()

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def components(self) -> dict[str, Any]:
        return dict(self._components)


if __name__ == "__main__":
    orchestrator = AppOrchestrator()
    asyncio.run(orchestrator.run())
