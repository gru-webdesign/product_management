"""Evidencija vremena: tajmer na zadatku i ručni unos sati.

Tajmer koji radi pamti se u podešavanjima (zadatak + vreme početka), pa preživljava zatvaranje
aplikacije. Kad postoje unosi vremena, „utrošeno" na zadatku je njihov zbir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Project, Task, TimeEntry
from app.services.defaults import get_setting, set_setting

TIMER_TASK = "timer_task_id"
TIMER_STARTED = "timer_started_at"
MIN_SECONDS = 60  # kraće od minuta se ne upisuje
MAX_HOURS = 24.0


@dataclass
class RunningTimer:
    task_id: str
    title: str
    project_id: str
    started_at: datetime

    def elapsed(self, now: datetime | None = None) -> timedelta:
        return (now or datetime.now(UTC)) - self.started_at


def running(session: Session) -> RunningTimer | None:
    task_id = get_setting(session, TIMER_TASK)
    started = get_setting(session, TIMER_STARTED)
    if not task_id or not started:
        return None
    task = session.get(Task, task_id)
    if task is None:  # zadatak je obrisan dok je tajmer radio
        _clear(session)
        return None
    try:
        started_at = datetime.fromisoformat(started)
    except ValueError:
        _clear(session)
        return None
    return RunningTimer(task.id, task.title, task.project_id, started_at)


def _clear(session: Session) -> None:
    set_setting(session, TIMER_TASK, "")
    set_setting(session, TIMER_STARTED, "")


def start(session: Session, task_id: str, now: datetime | None = None) -> TimeEntry | None:
    """Pokreće tajmer. Ako radi tajmer na drugom zadatku, prvo ga zaustavlja (vraća taj unos)."""
    if session.get(Task, task_id) is None:
        raise ValueError("Zadatak ne postoji.")
    now = now or datetime.now(UTC)
    current = running(session)
    stopped = None
    if current is not None:
        if current.task_id == task_id:
            return None
        stopped = stop(session, now)
    set_setting(session, TIMER_TASK, task_id)
    set_setting(session, TIMER_STARTED, now.isoformat())
    session.flush()
    return stopped


def stop(session: Session, now: datetime | None = None, note: str = "") -> TimeEntry | None:
    """Zaustavlja tajmer i upisuje vreme. Kraće od minuta se odbacuje (vraća None)."""
    current = running(session)
    if current is None:
        return None
    now = now or datetime.now(UTC)
    seconds = (now - current.started_at).total_seconds()
    _clear(session)
    if seconds < MIN_SECONDS:
        session.flush()
        return None
    hours = round(min(seconds / 3600, MAX_HOURS), 2)
    return add_entry(
        session, current.task_id, current.started_at.astimezone().date(), hours, note or "Tajmer"
    )


def discard(session: Session) -> None:
    _clear(session)
    session.flush()


def add_entry(
    session: Session,
    task_id: str,
    on: date,
    hours: float,
    note: str = "",
    rate_minor: int | None = None,
) -> TimeEntry:
    task = session.get(Task, task_id)
    if task is None:
        raise ValueError("Zadatak ne postoji.")
    if hours is None or hours <= 0:
        raise ValueError("Unesi broj sati veći od nule.")
    if hours > MAX_HOURS:
        raise ValueError("Jedan unos ne može biti duži od 24 sata.")
    if rate_minor is None:
        rate_minor = int(get_setting(session, "default_hourly_rate_minor") or 0)
    entry = TimeEntry(
        task_id=task_id,
        date=on,
        hours=round(float(hours), 2),
        hourly_rate_minor=rate_minor,
        note=note.strip(),
    )
    session.add(entry)
    session.flush()
    recalc(session, task)
    return entry


def delete_entry(session: Session, entry: TimeEntry) -> None:
    task = session.get(Task, entry.task_id)
    session.delete(entry)
    session.flush()
    if task is not None:
        recalc(session, task)


def entries(session: Session, task_id: str) -> list[TimeEntry]:
    return list(
        session.scalars(
            select(TimeEntry)
            .where(TimeEntry.task_id == task_id)
            .order_by(TimeEntry.date.desc(), TimeEntry.created_at.desc())
        )
    )


def total_hours(session: Session, task_id: str) -> float:
    return float(
        session.scalar(select(func.sum(TimeEntry.hours)).where(TimeEntry.task_id == task_id)) or 0.0
    )


def recalc(session: Session, task: Task) -> None:
    """Utrošeno na zadatku = zbir unosa vremena (ako unosa nema, ostaje ručna vrednost)."""
    total = total_hours(session, task.id)
    has_entries = (
        session.scalar(select(TimeEntry.id).where(TimeEntry.task_id == task.id).limit(1))
        is not None
    )
    if has_entries:
        task.actual_hours = round(total, 2)
    session.flush()


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def hours_by_project(session: Session, start: date, end: date) -> list[tuple[str, str, str, float]]:
    """(project_id, naziv, boja, sati) za period [start, end], najviše sati prvo."""
    rows = session.execute(
        select(Project.id, Project.name, Project.color, func.sum(TimeEntry.hours))
        .join(Task, Task.id == TimeEntry.task_id)
        .join(Project, Project.id == Task.project_id)
        .where(TimeEntry.date >= start, TimeEntry.date <= end)
        .group_by(Project.id)
        .order_by(func.sum(TimeEntry.hours).desc())
    ).all()
    return [(pid, name, color, float(h or 0)) for pid, name, color, h in rows]


def format_duration(td: timedelta) -> str:
    total = max(0, int(td.total_seconds()))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}"


def format_hours(hours: float) -> str:
    h = int(hours)
    m = round((hours - h) * 60)
    if m == 60:
        h, m = h + 1, 0
    return f"{h} h {m:02d} min" if m else f"{h} h"
