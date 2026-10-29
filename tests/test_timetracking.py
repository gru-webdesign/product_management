from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.services import projects as projects_svc
from app.services import tasks as tasks_svc
from app.services import timetracking as tt
from app.services.defaults import set_setting

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@pytest.fixture
def task(session):
    p = projects_svc.create(session, name="P")
    return tasks_svc.create(session, p.id, title="Dizajn")


def test_start_stop_records_entry(session, task):
    set_setting(session, "default_hourly_rate_minor", "250000")
    tt.start(session, task.id, now=T0)
    r = tt.running(session)
    assert r.task_id == task.id and r.title == "Dizajn"
    assert tt.format_duration(r.elapsed(T0 + timedelta(minutes=95, seconds=7))) == "1:35:07"
    entry = tt.stop(session, now=T0 + timedelta(minutes=90))
    assert entry.hours == 1.5 and entry.hourly_rate_minor == 250000 and entry.note == "Tajmer"
    assert task.actual_hours == 1.5
    assert tt.running(session) is None


def test_short_timer_is_discarded(session, task):
    tt.start(session, task.id, now=T0)
    assert tt.stop(session, now=T0 + timedelta(seconds=30)) is None
    assert tt.entries(session, task.id) == []


def test_starting_other_task_stops_first(session, task):
    other = tasks_svc.create(session, task.project_id, title="Razvoj")
    tt.start(session, task.id, now=T0)
    stopped = tt.start(session, other.id, now=T0 + timedelta(hours=2))
    assert stopped.task_id == task.id and stopped.hours == 2
    assert tt.running(session).task_id == other.id
    assert tt.start(session, other.id, now=T0 + timedelta(hours=3)) is None  # već radi


def test_manual_entries_and_validation(session, task):
    tt.add_entry(session, task.id, date(2026, 11, 2), 2.25, "sastanak")
    tt.add_entry(session, task.id, date(2026, 11, 3), 1)
    assert task.actual_hours == 3.25
    with pytest.raises(ValueError):
        tt.add_entry(session, task.id, date(2026, 11, 3), 0)
    with pytest.raises(ValueError):
        tt.add_entry(session, task.id, date(2026, 11, 3), 25)
    tt.delete_entry(session, tt.entries(session, task.id)[0])
    assert task.actual_hours == 2.25


def test_deleted_task_clears_timer(session, task):
    tt.start(session, task.id, now=T0)
    tasks_svc.delete(session, task)
    assert tt.running(session) is None


def test_hours_by_project_and_formatting(session, task):
    tt.add_entry(session, task.id, date(2026, 11, 2), 3)
    tt.add_entry(session, task.id, date(2026, 10, 20), 5)  # van nedelje
    rows = tt.hours_by_project(session, date(2026, 11, 2), date(2026, 11, 8))
    assert [(r[1], r[3]) for r in rows] == [("P", 3.0)]
    assert tt.week_start(date(2026, 11, 5)) == date(2026, 11, 2)
    assert tt.format_hours(1.5) == "1 h 30 min" and tt.format_hours(2) == "2 h"
    assert tt.format_hours(0.999) == "1 h"
