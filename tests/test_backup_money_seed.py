from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.db.models import CostEntry, Project, Task, TaskDependency
from app.main import bootstrap
from app.services import backup
from app.services.money import format_money, from_minor, to_base_minor, to_minor
from scripts.seed_demo import DEMO_NAME, seed


def test_backup_created_on_second_start_and_rotated(paths):
    db = bootstrap(paths)  # prvi start: baza ne postoji, nema backup-a
    db.dispose()
    assert backup.list_backups(paths) == []

    start = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(13):
        backup.create_backup(paths, keep=10, now=start + timedelta(minutes=i))
    files = backup.list_backups(paths)
    assert len(files) == 10
    assert files[0].name == "etapa-20260101-121200.db"


def test_backup_same_second(paths):
    bootstrap(paths).dispose()
    now = datetime(2026, 1, 1, 12, 0, 0)
    a = backup.create_backup(paths, now=now)
    b = backup.create_backup(paths, now=now)
    assert a != b and a.exists() and b.exists()


def test_money_helpers():
    assert to_minor("1234.565") == 123457
    assert from_minor(123457) == Decimal("1234.57")
    assert to_base_minor(to_minor(89), "117.2") == to_minor("10430.80")
    assert format_money(123456789) == "1.234.567,89 RSD"
    assert format_money(-50, "EUR") == "-0,50 EUR"
    assert format_money(0) == "0,00 RSD"


def test_seed_demo_and_reseed(session):
    seed(session, today=date(2026, 11, 2))
    session.commit()
    seed(session, today=date(2026, 11, 2))  # drugi put zamenjuje, ne duplira
    session.commit()

    assert session.scalar(select(func.count(Project.id)).where(Project.name == DEMO_NAME)) == 1
    assert session.scalar(select(func.count(Task.id))) == 10
    assert session.scalar(select(func.count(TaskDependency.id))) == 8
    figma = session.scalar(select(CostEntry).where(CostEntry.vendor == "Figma"))
    assert figma.amount_base_minor == to_minor("10430.80")
