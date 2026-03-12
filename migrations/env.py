"""Alembic environment configuration for traderj."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    return "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
        os.getenv("DB_USER", "traderj"),
        os.getenv("DB_PASSWORD", "changeme"),
        os.getenv("DB_HOST", "localhost"),
        os.getenv("DB_PORT", "5432"),
        os.getenv("DB_NAME", "traderj"),
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from asyncio import get_event_loop

    from sqlalchemy.ext.asyncio import create_async_engine

    connectable = create_async_engine(get_url())

    async def do_run_migrations() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_migrations)
        await connectable.dispose()

    def do_migrations(connection: object) -> None:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()

    loop = get_event_loop()
    loop.run_until_complete(do_run_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
