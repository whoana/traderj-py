"""FastAPI dependency injection — DataStore and service access.

Supports two modes:
  - Standalone: API creates its own DataStore + IPC client (original)
  - Embedded: Engine injects DataStore + TradingLoops directly (Fly.io)
"""

from __future__ import annotations

from typing import Any


class AppState:
    """Application state container for dependency injection."""

    def __init__(self) -> None:
        self.data_store: Any = None
        self.engine_client: Any = None  # IPC client to engine
        self.trading_loops: dict[str, Any] = {}  # strategy_id → TradingLoop
        self.event_bus: Any = None
        self.exchange: Any = None
        self.settings: Any = None
        self.embedded: bool = False  # True when running inside engine process

    def set_data_store(self, store: Any) -> None:
        self.data_store = store

    def set_engine_client(self, client: Any) -> None:
        self.engine_client = client

    def set_trading_loops(self, loops: dict[str, Any]) -> None:
        self.trading_loops = loops

    def set_event_bus(self, bus: Any) -> None:
        self.event_bus = bus

    def set_exchange(self, exchange: Any) -> None:
        self.exchange = exchange

    def set_settings(self, settings: Any) -> None:
        self.settings = settings


# Singleton state — set during app lifespan
app_state = AppState()


def get_store() -> Any:
    """Dependency: returns the DataStore instance."""
    if app_state.data_store is None:
        raise RuntimeError("DataStore not initialized")
    return app_state.data_store


def get_engine() -> Any:
    """Dependency: returns the engine IPC client."""
    return app_state.engine_client


def get_loops() -> dict[str, Any]:
    """Dependency: returns trading loops dict (embedded mode)."""
    return app_state.trading_loops


def get_exchange() -> Any:
    """Dependency: returns exchange client."""
    return app_state.exchange
