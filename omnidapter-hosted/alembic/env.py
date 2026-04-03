"""Alembic migration environment for omnidapter-hosted."""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection as SAConnection
from sqlalchemy.ext.asyncio import async_engine_from_config

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import server models (to pick up server tables in metadata)
# Import hosted models
import omnidapter_hosted.models  # noqa: F401, E402
import omnidapter_server.models  # noqa: F401, E402
from omnidapter_hosted.database import HostedBase  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Hosted migration only manages hosted tables; server tables are managed by
# the server migration and should be excluded from autogenerate comparison.
_hosted_table_names = set(HostedBase.metadata.tables.keys())
target_metadata = HostedBase.metadata


def include_object(object, name, type_, reflected, compare_to):  # noqa: A002
    if type_ == "table":
        return name in _hosted_table_names
    return True


def get_url() -> str:
    from omnidapter_server.config import get_settings

    return get_settings().omnidapter_database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: SAConnection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = get_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
