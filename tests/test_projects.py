from __future__ import annotations

from datetime import date

import pytest

from app.db.models import ProjectStatus, Task, TaskStatus
from app.services import activity
from app.services import projects as svc


def test_create_update_and_history(session):
    p = svc.create(session, name="  Sajt  ", client="Klijent")
    assert p.name == "Sajt"
    changed = svc.update(session, p, name="Sajt 2", status=ProjectStatus.ON_HOLD, client="Klijent")
    assert changed == ["name", "status"]
    hist = activity.history(session, p.id)
    fields = {h.field for h in hist}
    assert {"name", "status"} <= fields
    status_entry = next(h for h in hist if h.field == "status")
    assert (status_entry.old_value, status_entry.new_value) == ("Aktivan", "Na čekanju")


def test_validation(session):
    with pytest.raises(ValueError):
        svc.create(session, name="  ")
    with pytest.raises(ValueError):
        svc.create(session, name="X", start_date=date(2026, 5, 2), end_date=date(2026, 5, 1))
    with pytest.raises(ValueError):
        svc.create(session, name="X", nepostojece="a")
    p = svc.create(session, name="X")
    with pytest.raises(ValueError):
        svc.update(session, p, id="drugi")


def test_list_archive_and_order(session):
    a = svc.create(session, name="A")
    b = svc.create(session, name="B")
    assert [p.name for p in svc.list_projects(session)] == ["A", "B"]
    svc.set_archived(session, a, True)
    assert [p.name for p in svc.list_projects(session)] == ["B"]
    assert [p.name for p in svc.list_projects(session, include_archived=True)] == ["B", "A"]
    assert b.sort_order > a.sort_order


def test_progress(session):
    p = svc.create(session, name="P")
    assert svc.progress(session, p.id) == (0, 0, 0)
    session.add_all(
        [
            Task(project=p, title="a", status=TaskStatus.DONE, progress=30),
            Task(project=p, title="b", progress=50),
        ]
    )
    session.flush()
    assert svc.progress(session, p.id) == (1, 2, 75)


def test_delete(session):
    p = svc.create(session, name="Briši")
    session.add(Task(project=p, title="t"))
    session.flush()
    svc.delete(session, p)
    assert svc.list_projects(session, include_archived=True) == []
