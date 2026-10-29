"""SQLAlchemy osnova: deklarativna baza, zajednička polja i konekcija na SQLite."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, MetaData, String, TypeDecorator, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import Paths

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Imenovani constraint-i su potrebni da bi Alembic batch migracije na SQLite radile pouzdano.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class UTCDateTime(TypeDecorator):
    """Vreme se u bazi čuva kao UTC, a čita se nazad sa oznakom zone (UTC).

    SQLite ne pamti vremensku zonu, pa bi se bez ovoga vreme čitalo kao „lokalno" i
    prikazivalo pomereno za razliku od UTC-a (u Beogradu sat ili dva).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record) -> None:
    """Uključuje strane ključeve i WAL režim (brže i bezbednije pisanje)."""
    if type(dbapi_conn).__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


class Database:
    """Jedna lokalna baza aplikacije."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.engine = create_engine(paths.db_url, future=True)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._sessions()

    def upgrade(self, revision: str = "head") -> None:
        """Dovodi šemu baze na najnoviju verziju (Alembic)."""
        from alembic import command

        command.upgrade(alembic_config(self.paths.db_url), revision)

    def dispose(self) -> None:
        self.engine.dispose()


def alembic_config(db_url: str):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg
