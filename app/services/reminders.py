"""Podsetnici za rokove: zadaci i milestone-i danas, sutra ili koji kasne.

Svaki podsetnik se prikazuje najviše jednom dnevno (pamti se u podešavanjima).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Milestone, Project, Task, TaskStatus
from app.services.defaults import get_setting, set_setting

SENT = "reminders_sent"
ENABLED = "reminders_enabled"


@dataclass
class Reminder:
    key: str
    project_id: str
    task_id: str | None
    title: str
    when: str  # "danas" / "sutra" / "kasni"


def enabled(session: Session) -> bool:
    return get_setting(session, ENABLED) != "0"


def due(session: Session, today: date | None = None) -> list[Reminder]:
    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    out: list[Reminder] = []
    tasks = session.execute(
        select(Task, Project)
        .join(Project, Project.id == Task.project_id)
        .where(
            Project.archived.is_(False),
            Task.status != TaskStatus.DONE,
            Task.due_date.is_not(None),
            Task.due_date <= tomorrow,
        )
        .order_by(Task.due_date)
    ).all()
    for t, p in tasks:
        when = "kasni" if t.due_date < today else ("danas" if t.due_date == today else "sutra")
        out.append(Reminder(f"task:{t.id}:{when}", p.id, t.id, t.title, when))
    milestones = session.execute(
        select(Milestone, Project)
        .join(Project, Project.id == Milestone.project_id)
        .where(
            Project.archived.is_(False),
            Milestone.done.is_(False),
            Milestone.date >= today,
            Milestone.date <= tomorrow,
        )
    ).all()
    for m, p in milestones:
        when = "danas" if m.date == today else "sutra"
        out.append(Reminder(f"ms:{m.id}:{when}", p.id, None, f"Milestone: {m.name}", when))
    return out


def _sent(session: Session) -> dict[str, str]:
    try:
        return json.loads(get_setting(session, SENT) or "{}")
    except ValueError:
        return {}


def pending(session: Session, today: date | None = None) -> list[Reminder]:
    """Podsetnici koji danas još nisu prikazani."""
    today = today or date.today()
    sent = _sent(session)
    return [r for r in due(session, today) if sent.get(r.key) != today.isoformat()]


def mark_sent(session: Session, reminders: list[Reminder], today: date | None = None) -> None:
    today = today or date.today()
    sent = {k: v for k, v in _sent(session).items() if v >= (today - timedelta(days=7)).isoformat()}
    for r in reminders:
        sent[r.key] = today.isoformat()
    set_setting(session, SENT, json.dumps(sent))
    session.flush()


def summarize(reminders: list[Reminder]) -> tuple[str, str]:
    """(naslov, tekst) za jednu sistemsku notifikaciju."""
    late = [r for r in reminders if r.when == "kasni"]
    today = [r for r in reminders if r.when == "danas"]
    tomorrow = [r for r in reminders if r.when == "sutra"]
    parts = []
    if late:
        parts.append(f"Kasni: {len(late)}")
    if today:
        parts.append(f"rok danas: {len(today)}")
    if tomorrow:
        parts.append(f"rok sutra: {len(tomorrow)}")
    title = "Rokovi: " + ", ".join(parts)
    names = [r.title for r in (late + today + tomorrow)[:4]]
    more = len(reminders) - len(names)
    body = "\n".join(names) + (f"\ni još {more}" if more > 0 else "")
    return title, body
