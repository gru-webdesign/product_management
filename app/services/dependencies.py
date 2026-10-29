"""Zavisnosti između zadataka i automatsko pomeranje zavisnih zadataka.

Računa se u kalendarskim danima (vikendi se ne preskaču). Zavisni zadatak se samo pomera
UNAPRED kad bi prekršio zavisnost; nikad se sam ne vraća unazad. Trajanje se čuva.

Tipovi:
- FS (završi → počni): naslednik počinje najranije dan posle kraja prethodnika (+ kašnjenje)
- SS (počni → počni): naslednik počinje najranije kad i prethodnik (+ kašnjenje)
- FF (završi → završi): naslednik se završava najranije kad i prethodnik (+ kašnjenje)
"""

from __future__ import annotations

from collections import deque
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DependencyType, Task, TaskDependency
from app.services import activity


def span(task: Task) -> tuple[date, date] | None:
    """(početak, kraj) zadatka; zadatak sa samo jednim datumom traje jedan dan."""
    start = task.start_date or task.due_date
    end = task.due_date or task.start_date
    if start is None or end is None:
        return None
    return start, end


def would_create_cycle(session: Session, predecessor_id: str, successor_id: str) -> bool:
    """Da li bi veza predecessor → successor napravila krug (successor već vodi do njega)."""
    if predecessor_id == successor_id:
        return True
    seen = {successor_id}
    queue = deque([successor_id])
    while queue:
        current = queue.popleft()
        nexts = session.scalars(
            select(TaskDependency.successor_id).where(TaskDependency.predecessor_id == current)
        )
        for nxt in nexts:
            if nxt == predecessor_id:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def add(
    session: Session,
    predecessor: Task,
    successor: Task,
    type: DependencyType = DependencyType.FINISH_TO_START,
    lag_days: int = 0,
) -> TaskDependency:
    if predecessor.id == successor.id:
        raise ValueError("Zadatak ne može da zavisi sam od sebe.")
    if predecessor.project_id != successor.project_id:
        raise ValueError("Zavisnost može da postoji samo između zadataka istog projekta.")
    exists = session.scalar(
        select(TaskDependency.id).where(
            TaskDependency.predecessor_id == predecessor.id,
            TaskDependency.successor_id == successor.id,
        )
    )
    if exists:
        raise ValueError("Ova zavisnost već postoji.")
    if would_create_cycle(session, predecessor.id, successor.id):
        raise ValueError(
            f"„{successor.title}“ već (posredno) prethodi zadatku „{predecessor.title}“ — "
            "veza bi napravila krug."
        )
    dep = TaskDependency(predecessor=predecessor, successor=successor, type=type, lag_days=lag_days)
    session.add(dep)
    session.flush()
    activity.log(
        session,
        "task",
        successor.id,
        "update",
        successor.project_id,
        "dependency",
        None,
        predecessor.title,
    )
    propagate(session, predecessor)
    return dep


def remove(session: Session, dep: TaskDependency) -> None:
    successor = session.get(Task, dep.successor_id)
    predecessor = session.get(Task, dep.predecessor_id)
    if successor and predecessor:
        activity.log(
            session,
            "task",
            successor.id,
            "update",
            successor.project_id,
            "dependency",
            predecessor.title,
            None,
        )
    session.delete(dep)
    session.flush()


def required_shift(dep: TaskDependency, predecessor: Task, successor: Task) -> int:
    """Za koliko dana naslednik mora unapred (0 ako je zavisnost već ispunjena)."""
    p, s = span(predecessor), span(successor)
    if p is None or s is None:
        return 0
    lag = timedelta(days=dep.lag_days or 0)
    if dep.type == DependencyType.FINISH_TO_START:
        earliest, actual = p[1] + timedelta(days=1) + lag, s[0]
    elif dep.type == DependencyType.START_TO_START:
        earliest, actual = p[0] + lag, s[0]
    else:  # FINISH_TO_FINISH
        earliest, actual = p[1] + lag, s[1]
    return max(0, (earliest - actual).days)


def shift(session: Session, task: Task, days: int) -> None:
    if not days:
        return
    delta = timedelta(days=days)
    old_start, old_due = task.start_date, task.due_date
    if task.start_date:
        task.start_date += delta
    if task.due_date:
        task.due_date += delta
    if old_start != task.start_date:
        activity.log(
            session,
            "task",
            task.id,
            "update",
            task.project_id,
            "start_date",
            old_start,
            task.start_date,
        )
    if old_due != task.due_date:
        activity.log(
            session, "task", task.id, "update", task.project_id, "due_date", old_due, task.due_date
        )


def propagate(session: Session, task: Task, _depth: int = 0) -> list[Task]:
    """Pomera naslednike koji krše zavisnosti, rekurzivno. Vraća pomerene zadatke."""
    if _depth > 500:  # zaštita; krugovi su ionako zabranjeni pri dodavanju
        return []
    moved: list[Task] = []
    session.flush()
    outgoing = session.scalars(
        select(TaskDependency).where(TaskDependency.predecessor_id == task.id)
    )
    for dep in list(outgoing):
        successor = dep.successor
        days = required_shift(dep, task, successor)
        if days:
            shift(session, successor, days)
            moved.append(successor)
            moved.extend(propagate(session, successor, _depth + 1))
    session.flush()
    return moved


def for_project(session: Session, project_id: str) -> list[TaskDependency]:
    stmt = (
        select(TaskDependency)
        .join(Task, Task.id == TaskDependency.successor_id)
        .where(Task.project_id == project_id)
    )
    return list(session.scalars(stmt))
