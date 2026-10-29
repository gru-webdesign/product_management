"""Projekti: pravljenje, izmena, arhiviranje, brisanje."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Project, Task, TaskStatus
from app.services import activity

EDITABLE = {
    "name",
    "description",
    "client",
    "color",
    "start_date",
    "end_date",
    "status",
    "archived",
    "sort_order",
}


def _validate(fields: dict[str, Any], current: Project | None = None) -> None:
    name = fields.get("name", current.name if current else None)
    if not name or not str(name).strip():
        raise ValueError("Naziv projekta je obavezan")
    start = fields.get("start_date", current.start_date if current else None)
    end = fields.get("end_date", current.end_date if current else None)
    if start and end and start > end:
        raise ValueError("Početak projekta mora biti pre kraja")


def list_projects(session: Session, include_archived: bool = False) -> list[Project]:
    stmt = select(Project).order_by(Project.archived, Project.sort_order, Project.created_at)
    if not include_archived:
        stmt = stmt.where(Project.archived.is_(False))
    return list(session.scalars(stmt))


def get(session: Session, project_id: str) -> Project | None:
    return session.get(Project, project_id)


def create(session: Session, **fields: Any) -> Project:
    unknown = set(fields) - EDITABLE
    if unknown:
        raise ValueError(f"Nepoznata polja: {', '.join(sorted(unknown))}")
    fields["name"] = str(fields.get("name", "")).strip()
    _validate(fields)
    if "sort_order" not in fields:
        fields["sort_order"] = (session.scalar(select(func.max(Project.sort_order))) or 0) + 1
    project = Project(**fields)
    session.add(project)
    session.flush()
    activity.log(session, "project", project.id, "create", project.id)
    return project


def update(session: Session, project: Project, **changes: Any) -> list[str]:
    if "name" in changes:
        changes["name"] = str(changes["name"]).strip()
    _validate(changes, project)
    changed = activity.apply_changes(session, project, changes, "project", project.id, EDITABLE)
    session.flush()
    return changed


def set_archived(session: Session, project: Project, archived: bool) -> None:
    update(session, project, archived=archived)


def delete(session: Session, project: Project) -> None:
    activity.log(session, "project", project.id, "delete", None, "name", project.name, None)
    session.delete(project)
    session.flush()


def progress(session: Session, project_id: str) -> tuple[int, int, int]:
    """(završeni zadaci, ukupno zadataka, prosečan progres 0–100) — samo zadaci najvišeg nivoa."""
    rows = session.execute(
        select(Task.status, Task.progress).where(
            Task.project_id == project_id, Task.parent_id.is_(None)
        )
    ).all()
    if not rows:
        return 0, 0, 0
    done = sum(1 for status, _ in rows if status == TaskStatus.DONE)
    avg = round(sum(100 if s == TaskStatus.DONE else p for s, p in rows) / len(rows))
    return done, len(rows), avg
