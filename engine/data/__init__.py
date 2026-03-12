"""Data store factory.

Provides ``create_data_store()`` to instantiate the configured DataStore backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.config.settings import DatabaseSettings


def create_data_store(db_settings: DatabaseSettings):
    """Create a DataStore based on ``db_settings.type``.

    Uses lazy imports so that ``asyncpg`` is not required when using SQLite.
    """
    if db_settings.type == "sqlite":
        from engine.data.sqlite_store import SqliteDataStore

        return SqliteDataStore(db_path=db_settings.sqlite_path)
    elif db_settings.type == "postgres":
        from engine.data.postgres_store import PostgresDataStore

        return PostgresDataStore(dsn=db_settings.url)
    else:
        raise ValueError(f"Unknown db type: {db_settings.type!r}")
