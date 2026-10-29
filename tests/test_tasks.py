from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.models import Priority, TaskStatus
from app.services import activity
from app.services import projects as projects_svc
from app.services import tasks as svc
from app.services.tasks import TaskFilter

D = date(2026, 11, 2)


@pytest.fixture
def project(session):
    return projects_svc.create(session, name="P")


def test_create_with_defaults_and_order(session, project):
    a = svc.create(session, project.id, title=" Prvi ")
    b = svc.create(session, project.id, title="Drugi")
    assert a.title == "Prvi" and a.status == TaskStatus.TODO and a.priority == Priority.MEDIUM
    assert b.sort_order > a.sort_order
    child = svc.create(session, project.id, title="Dete", parent_id=a.id)
    assert child.sort_order == 1
    assert [t.title for t, _ in svc.tree(session, project.id)] == ["Prvi", "Dete", "Drugi"]
    assert [d for _, d in svc.tree(session, project.id)] == [0, 1, 0]


def test_validation(session, project):
    with pytest.raises(ValueError):
        svc.create(session, project.id, title="")
    with pytest.raises(ValueError):
        svc.create(session, project.id, title="x", start_date=D, due_date=D - timedelta(days=1))
    with pytest.raises(ValueError):
        svc.create(session, project.id, title="x", estimate_hours=-1)
    other = projects_svc.create(session, name="Drugi")
    foreign = svc.create(session, other.id, title="tuđi")
    with pytest.raises(ValueError):
        svc.create(session, project.id, title="x", parent_id=foreign.id)


def test_cannot_be_own_ancestor(session, project):
    a = svc.create(session, project.id, title="a")
    b = svc.create(session, project.id, title="b", parent_id=a.id)
    c = svc.create(session, project.id, title="c", parent_id=b.id)
    with pytest.raises(ValueError):
        svc.update(session, a, parent_id=c.id)
    with pytest.raises(ValueError):
        svc.update(session, a, parent_id=a.id)


def test_done_sets_progress_and_history(session, project):
    t = svc.create(session, project.id, title="t", progress=20)
    changed = svc.update(session, t, status=TaskStatus.DONE)
    assert t.progress == 100 and set(changed) == {"status", "progress"}
    fields = [h.field for h in activity.history(session, t.id)]
    assert "status" in fields and "progress" in fields
    svc.update(session, t, progress=150)
    assert t.progress == 100


def test_tags(session, project):
    t = svc.create(session, project.id, title="t", tags=["Dizajn", "dizajn", " klijent "])
    assert sorted(x.name for x in t.tags) == ["dizajn", "klijent"]
    assert svc.update(session, t, tags=["klijent", "dizajn"]) == []
    assert svc.update(session, t, tags=["razvoj"]) == ["tags"]
    assert svc.all_tags(session) == ["dizajn", "klijent", "razvoj"]


def test_filters(session, project):
    svc.create(session, project.id, title="Kasni", due_date=D - timedelta(days=2))
    svc.create(
        session,
        project.id,
        title="Ove nedelje",
        due_date=D + timedelta(days=3),
        priority=Priority.URGENT,
    )
    svc.create(session, project.id, title="Bez roka", description="logo i boje", tags=["dizajn"])
    svc.create(
        session, project.id, title="Gotov", status=TaskStatus.DONE, due_date=D - timedelta(days=5)
    )

    def names(**kw):
        f = TaskFilter(**kw)
        tasks = [t for t, _ in svc.tree(session, project.id) if svc.matches(t, f, today=D)]
        return [t.title for t in tasks]

    assert names(due="overdue") == ["Kasni"]
    assert names(due="week") == ["Ove nedelje"]
    assert names(due="none") == ["Bez roka"]
    assert names(priority=Priority.URGENT) == ["Ove nedelje"]
    assert names(search="LOGO") == ["Bez roka"]
    assert names(tag="dizajn") == ["Bez roka"]
    assert names(hide_done=True) == ["Kasni", "Ove nedelje", "Bez roka"]
    assert names(status=TaskStatus.DONE) == ["Gotov"]
    assert not TaskFilter().active() and TaskFilter(search="x").active()


def test_notes(session, project):
    t = svc.create(session, project.id, title="t")
    svc.add_note(session, t, "prva")
    svc.add_note(session, t, "druga")
    assert len(svc.notes(session, t.id)) == 2
    with pytest.raises(ValueError):
        svc.add_note(session, t, "   ")


def test_move_up_down(session, project):
    svc.create(session, project.id, title="a")
    b = svc.create(session, project.id, title="b")
    assert svc.move(session, b, -1)
    assert [t.title for t, _ in svc.tree(session, project.id)] == ["b", "a"]
    assert not svc.move(session, b, -1)


def test_delete_cascades_subtasks(session, project):
    a = svc.create(session, project.id, title="a")
    svc.create(session, project.id, title="b", parent_id=a.id)
    svc.delete(session, a)
    assert svc.tree(session, project.id) == []
