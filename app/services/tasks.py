"""Zadaci: CRUD, podzadaci, tagovi, beleške, filteri, redosled."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Note, Priority, Tag, Task, TaskStatus
from app.services import activity, dependencies

EDITABLE = {
    "title",
    "description",
    "status",
    "priority",
    "start_date",
    "due_date",
    "estimate_hours",
    "actual_hours",
    "progress",
    "planned_cost_minor",
    "sort_order",
    "parent_id",
}


@dataclass
class TaskFilter:
    search: str = ""
    status: TaskStatus | None = None
    priority: Priority | None = None
    due: str = ""  # "" | "overdue" | "week" | "none"
    tag: str = ""
    hide_done: bool = False

    def active(self) -> bool:
        return bool(
            self.search or self.status or self.priority or self.due or self.tag or self.hide_done
        )


def is_overdue(task: Task, today: date | None = None) -> bool:
    today = today or date.today()
    return task.due_date is not None and task.due_date < today and task.status != TaskStatus.DONE


def _normalize(changes: dict[str, Any]) -> dict[str, Any]:
    if "title" in changes:
        changes["title"] = str(changes["title"]).strip()
    if "progress" in changes and changes["progress"] is not None:
        changes["progress"] = max(0, min(100, int(changes["progress"])))
    if changes.get("status") == TaskStatus.DONE and "progress" not in changes:
        changes["progress"] = 100
    for key in ("estimate_hours", "actual_hours"):
        if key in changes and changes[key] is not None and changes[key] < 0:
            raise ValueError("Broj sati ne može biti negativan.")
    if "planned_cost_minor" in changes and (changes["planned_cost_minor"] or 0) < 0:
        raise ValueError("Planirani trošak ne može biti negativan.")
    return changes


def _validate(session: Session, values: dict[str, Any], task: Task | None = None) -> None:
    title = values.get("title", task.title if task else "")
    if not title:
        raise ValueError("Naziv zadatka je obavezan.")
    start = values.get("start_date", task.start_date if task else None)
    due = values.get("due_date", task.due_date if task else None)
    if start and due and start > due:
        raise ValueError("Početak zadatka mora biti pre roka.")
    parent_id = values.get("parent_id", task.parent_id if task else None)
    if parent_id:
        parent = session.get(Task, parent_id)
        project_id = values.get("project_id", task.project_id if task else None)
        if parent is None or parent.project_id != project_id:
            raise ValueError("Nadređeni zadatak mora biti iz istog projekta.")
        if task is not None and (parent_id == task.id or parent_id in descendant_ids(task)):
            raise ValueError("Zadatak ne može biti podzadatak samog sebe ili svog podzadatka.")


def descendant_ids(task: Task) -> set[str]:
    out: set[str] = set()
    stack = list(task.subtasks)
    while stack:
        t = stack.pop()
        out.add(t.id)
        stack.extend(t.subtasks)
    return out


def _next_order(session: Session, project_id: str, parent_id: str | None) -> int:
    stmt = select(func.max(Task.sort_order)).where(Task.project_id == project_id)
    stmt = stmt.where(
        Task.parent_id.is_(None) if parent_id is None else Task.parent_id == parent_id
    )
    return (session.scalar(stmt) or 0) + 1


def get(session: Session, task_id: str) -> Task | None:
    return session.get(Task, task_id)


def create(session: Session, project_id: str, tags: list[str] | None = None, **fields) -> Task:
    unknown = set(fields) - EDITABLE
    if unknown:
        raise ValueError(f"Nepoznata polja: {', '.join(sorted(unknown))}")
    fields = _normalize(dict(fields))
    _validate(session, {**fields, "project_id": project_id})
    if "sort_order" not in fields:
        fields["sort_order"] = _next_order(session, project_id, fields.get("parent_id"))
    task = Task(project_id=project_id, **fields)
    session.add(task)
    session.flush()
    if tags:
        set_tags(session, task, tags, log=False)
    activity.log(session, "task", task.id, "create", project_id)
    return task


def update(session: Session, task: Task, **changes) -> list[str]:
    tags = changes.pop("tags", None)
    changes = _normalize(changes)
    _validate(session, changes, task)
    if "parent_id" in changes and changes["parent_id"] != task.parent_id:
        changes.setdefault(
            "sort_order", _next_order(session, task.project_id, changes["parent_id"])
        )
    changed = activity.apply_changes(session, task, changes, "task", task.project_id, EDITABLE)
    if tags is not None and set_tags(session, task, tags):
        changed.append("tags")
    session.flush()
    if {"start_date", "due_date"} & set(changed):
        dependencies.propagate(session, task)
    return changed


def set_dates(session: Session, task: Task, start: date | None, due: date | None) -> list[Task]:
    """Promena datuma (npr. prevlačenjem na Gantu). Vraća zadatke pomerene zbog zavisnosti."""
    _validate(session, {"start_date": start, "due_date": due}, task)
    activity.apply_changes(
        session, task, {"start_date": start, "due_date": due}, "task", task.project_id, EDITABLE
    )
    session.flush()
    return dependencies.propagate(session, task)


def move_by_days(session: Session, task: Task, days: int) -> list[Task]:
    delta = timedelta(days=days)
    start = task.start_date + delta if task.start_date else None
    due = task.due_date + delta if task.due_date else None
    return set_dates(session, task, start, due)


def set_status(session: Session, task: Task, status: TaskStatus) -> None:
    update(session, task, status=status)


def delete(session: Session, task: Task) -> None:
    activity.log(session, "task", task.id, "delete", task.project_id, "title", task.title, None)
    session.delete(task)
    session.flush()


def set_tags(session: Session, task: Task, names: list[str], log: bool = True) -> bool:
    clean = []
    for n in names:
        n = n.strip().lower()
        if n and n not in clean:
            clean.append(n)
    old = sorted(t.name for t in task.tags)
    if sorted(clean) == old:
        return False
    tags = []
    for name in clean:
        tag = session.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
        tags.append(tag)
    task.tags = tags
    if log:
        activity.log(
            session,
            "task",
            task.id,
            "update",
            task.project_id,
            "tags",
            ", ".join(old),
            ", ".join(sorted(clean)),
        )
    session.flush()
    return True


def all_tags(session: Session) -> list[str]:
    return list(session.scalars(select(Tag.name).order_by(Tag.name)))


def add_note(session: Session, task: Task, text: str) -> Note:
    text = text.strip()
    if not text:
        raise ValueError("Beleška je prazna.")
    note = Note(task_id=task.id, text=text)
    session.add(note)
    session.flush()
    return note


def delete_note(session: Session, note: Note) -> None:
    session.delete(note)
    session.flush()


def notes(session: Session, task_id: str) -> list[Note]:
    return list(
        session.scalars(
            select(Note).where(Note.task_id == task_id).order_by(Note.created_at.desc())
        )
    )


# --- čitanje -------------------------------------------------------------------------------------


def project_tasks(session: Session, project_id: str) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .options(selectinload(Task.tags), selectinload(Task.subtasks))
        .order_by(Task.sort_order, Task.created_at)
    )
    return list(session.scalars(stmt))


def tree(session: Session, project_id: str) -> list[tuple[Task, int]]:
    """Zadaci u redosledu stabla (roditelj pa njegova deca), sa dubinom."""
    tasks = project_tasks(session, project_id)
    children: dict[str | None, list[Task]] = {}
    for t in tasks:
        children.setdefault(t.parent_id, []).append(t)
    out: list[tuple[Task, int]] = []

    def walk(parent_id: str | None, depth: int) -> None:
        for t in children.get(parent_id, []):
            out.append((t, depth))
            walk(t.id, depth + 1)

    walk(None, 0)
    return out


def matches(task: Task, f: TaskFilter, today: date | None = None) -> bool:
    today = today or date.today()
    if f.hide_done and task.status == TaskStatus.DONE:
        return False
    if f.status and task.status != f.status:
        return False
    if f.priority and task.priority != f.priority:
        return False
    if f.tag and f.tag not in {t.name for t in task.tags}:
        return False
    if f.due == "overdue" and not is_overdue(task, today):
        return False
    if f.due == "week":
        if task.due_date is None or not (today <= task.due_date <= today + timedelta(days=7)):
            return False
    if f.due == "none" and task.due_date is not None:
        return False
    if f.search:
        needle = f.search.lower()
        hay = f"{task.title}\n{task.description}\n{' '.join(t.name for t in task.tags)}".lower()
        if needle not in hay:
            return False
    return True


def filtered(session: Session, project_id: str, f: TaskFilter) -> list[Task]:
    return [t for t, _ in tree(session, project_id) if matches(t, f)]


def search_all(session: Session, text: str, limit: int = 50) -> list[Task]:
    like = f"%{text.strip()}%"
    stmt = (
        select(Task).where(or_(Task.title.ilike(like), Task.description.ilike(like))).limit(limit)
    )
    return list(session.scalars(stmt))


def move(session: Session, task: Task, direction: int) -> bool:
    """Pomera zadatak gore (-1) ili dole (+1) među zadacima istog roditelja."""
    stmt = select(Task).where(Task.project_id == task.project_id)
    stmt = stmt.where(
        Task.parent_id.is_(None) if task.parent_id is None else Task.parent_id == task.parent_id
    )
    siblings = list(session.scalars(stmt.order_by(Task.sort_order, Task.created_at)))
    i = siblings.index(task)
    j = i + direction
    if not 0 <= j < len(siblings):
        return False
    siblings[i], siblings[j] = siblings[j], siblings[i]
    for order, t in enumerate(siblings):
        t.sort_order = order
    session.flush()
    return True
