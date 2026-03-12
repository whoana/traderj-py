"""FastAPI dependency injection — DataStore and service access."""

from __future__ import annotations

from typing import Any


class AppState:
    """Application state container for dependency injection."""

    def __init__(self) -> None:
        self.data_store: Any = None
        self.engine_client: Any = None  # IPC client to engine

    def set_data_store(self, store: Any) -> None:
        self.data_store = store

    def set_engine_client(self, client: Any) -> None:
        self.engine_client = client


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
