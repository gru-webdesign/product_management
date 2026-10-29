from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.models import DependencyType
from app.services import dependencies as deps
from app.services import projects as projects_svc
from app.services import tasks as tasks_svc

D = date(2026, 11, 2)


def day(n: int) -> date:
    return D + timedelta(days=n)


@pytest.fixture
def chain(session):
    p = projects_svc.create(session, name="P")
    a = tasks_svc.create(session, p.id, title="A", start_date=day(0), due_date=day(2))
    b = tasks_svc.create(session, p.id, title="B", start_date=day(3), due_date=day(5))
    c = tasks_svc.create(session, p.id, title="C", start_date=day(6), due_date=day(6))
    deps.add(session, a, b)
    deps.add(session, b, c)
    return p, a, b, c


def test_no_shift_when_satisfied(session, chain):
    _, a, b, c = chain
    assert (b.start_date, c.start_date) == (day(3), day(6))


def test_moving_predecessor_pushes_chain_keeping_duration(session, chain):
    _, a, b, c = chain
    moved = tasks_svc.move_by_days(session, a, 4)  # A: 4–6 → B mora od 7
    assert [t.title for t in moved] == ["B", "C"]
    assert (b.start_date, b.due_date) == (day(7), day(9))
    assert (c.start_date, c.due_date) == (day(10), day(10))


def test_moving_back_does_not_pull(session, chain):
    _, a, b, _ = chain
    tasks_svc.move_by_days(session, a, -2)
    assert b.start_date == day(3)


def test_resize_end_pushes(session, chain):
    _, a, b, _ = chain
    tasks_svc.set_dates(session, a, day(0), day(4))
    assert b.start_date == day(5)


def test_update_dates_through_update_also_propagates(session, chain):
    _, a, b, _ = chain
    tasks_svc.update(session, a, due_date=day(3))
    assert b.start_date == day(4)


def test_cycle_and_duplicates_rejected(session, chain):
    p, a, b, c = chain
    with pytest.raises(ValueError, match="krug"):
        deps.add(session, c, a)
    with pytest.raises(ValueError, match="već postoji"):
        deps.add(session, a, b)
    with pytest.raises(ValueError):
        deps.add(session, a, a)
    other = projects_svc.create(session, name="Drugi")
    x = tasks_svc.create(session, other.id, title="X")
    with pytest.raises(ValueError):
        deps.add(session, a, x)


def test_adding_dependency_shifts_successor(session):
    p = projects_svc.create(session, name="P")
    a = tasks_svc.create(session, p.id, title="A", start_date=day(0), due_date=day(5))
    b = tasks_svc.create(session, p.id, title="B", start_date=day(2), due_date=day(3))
    deps.add(session, a, b, lag_days=1)
    assert (b.start_date, b.due_date) == (day(7), day(8))


def test_ss_and_ff(session):
    p = projects_svc.create(session, name="P")
    a = tasks_svc.create(session, p.id, title="A", start_date=day(4), due_date=day(8))
    b = tasks_svc.create(session, p.id, title="B", start_date=day(0), due_date=day(2))
    c = tasks_svc.create(session, p.id, title="C", start_date=day(0), due_date=day(3))
    deps.add(session, a, b, DependencyType.START_TO_START)
    deps.add(session, a, c, DependencyType.FINISH_TO_FINISH)
    assert b.start_date == day(4)
    assert c.due_date == day(8) and c.start_date == day(5)


def test_tasks_without_dates_are_ignored(session):
    p = projects_svc.create(session, name="P")
    a = tasks_svc.create(session, p.id, title="A")
    b = tasks_svc.create(session, p.id, title="B", start_date=day(0), due_date=day(1))
    deps.add(session, a, b)
    assert b.start_date == day(0)
    assert len(deps.for_project(session, p.id)) == 1


def test_remove(session, chain):
    p, a, b, _ = chain
    dep = a.successors[0]
    deps.remove(session, dep)
    assert len(deps.for_project(session, p.id)) == 1
