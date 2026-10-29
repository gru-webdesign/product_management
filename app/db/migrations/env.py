"""Alembic okruženje. render_as_batch je obavezan za SQLite (ALTER TABLE je ograničen)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from app.db import models  # noqa: F401  (registruje sve tabele u metadata)
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def _db_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from app.config import get_paths

    return get_paths().ensure().db_url


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(_db_url())
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
