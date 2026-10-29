from __future__ import annotations

from datetime import date

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.models import (
    BudgetCategory,
    Note,
    Project,
    Setting,
    Task,
    TaskDependency,
    TaskStatus,
)
from app.services.defaults import DEFAULT_CATEGORIES, ensure_defaults, get_setting


def test_migrations_match_models(db):
    """Migracije prave tačno ono što opisuju modeli (nema zaboravljene migracije)."""
    with db.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_all_tables_exist(db):
    tables = set(inspect(db.engine).get_table_names())
    assert set(Base.metadata.tables) <= tables


def test_defaults_created_once(session):
    ensure_defaults(session)
    ensure_defaults(session)
    names = list(session.scalars(select(BudgetCategory.name).order_by(BudgetCategory.sort_order)))
    assert names == [n for n, _ in DEFAULT_CATEGORIES]
    assert get_setting(session, "base_currency") == "RSD"


def test_defaults_keep_user_values(session):
    session.get(Setting, "base_currency").value = "EUR"
    session.commit()
    ensure_defaults(session)
    assert get_setting(session, "base_currency") == "EUR"


def test_project_with_tasks_and_cascade_delete(session):
    p = Project(name="Test")
    parent = Task(project=p, title="Roditelj")
    child = Task(project=p, title="Dete", parent=parent)
    session.add_all([p, parent, child])
    session.flush()
    session.add(Note(task=child, text="beleška"))
    session.add(TaskDependency(predecessor=parent, successor=child))
    session.commit()

    assert len(p.id) == 36
    assert parent.status == TaskStatus.TODO
    assert child.parent_id == parent.id

    session.delete(p)
    session.commit()
    assert session.scalar(select(Task.id)) is None
    assert session.scalar(select(Note.id)) is None
    assert session.scalar(select(TaskDependency.id)) is None


def test_dependency_rules(session):
    p = Project(name="Zavisnosti")
    a, b = Task(project=p, title="A"), Task(project=p, title="B")
    session.add_all([p, a, b])
    session.commit()

    session.add(TaskDependency(predecessor=a, successor=a))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(TaskDependency(predecessor_id=a.id, successor_id=b.id))
    session.commit()
    session.add(TaskDependency(predecessor_id=a.id, successor_id=b.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_task_constraints(session):
    p = Project(name="Pravila")
    session.add(p)
    session.add(
        Task(project=p, title="Loši datumi", start_date=date(2026, 5, 2), due_date=date(2026, 5, 1))
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(Task(project_id=p.id, title="Loš progres", progress=150))
    with pytest.raises(IntegrityError):
        session.commit()


def test_upgrade_is_idempotent(db):
    db.upgrade()
    db.upgrade()


def test_datetimes_come_back_as_utc_aware(session):
    """SQLite ne čuva zonu; bez UTCDateTime vreme bi se prikazalo pomereno za UTC razliku."""
    from datetime import UTC, datetime, timedelta, timezone

    p = Project(name="Vreme")
    session.add(p)
    session.commit()
    session.expire_all()
    loaded = session.get(Project, p.id)
    assert loaded.created_at.tzinfo is not None
    assert abs(loaded.created_at - datetime.now(UTC)) < timedelta(minutes=1)
    belgrade = timezone(timedelta(hours=1))
    loaded.updated_at = datetime(2026, 11, 2, 12, 0, tzinfo=belgrade)
    session.commit()
    session.expire_all()
    assert session.get(Project, p.id).updated_at == datetime(2026, 11, 2, 11, 0, tzinfo=UTC)
