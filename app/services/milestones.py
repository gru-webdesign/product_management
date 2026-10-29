"""Milestone-i (ključni datumi projekta)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Milestone
from app.services import activity

EDITABLE = {"name", "date", "done"}


def for_project(session: Session, project_id: str) -> list[Milestone]:
    return list(
        session.scalars(
            select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.date)
        )
    )


def create(session: Session, project_id: str, name: str, on: date, done: bool = False) -> Milestone:
    name = name.strip()
    if not name:
        raise ValueError("Naziv milestone-a je obavezan.")
    m = Milestone(project_id=project_id, name=name, date=on, done=done)
    session.add(m)
    session.flush()
    activity.log(session, "milestone", m.id, "create", project_id)
    return m


def update(session: Session, m: Milestone, **changes) -> list[str]:
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise ValueError("Naziv milestone-a je obavezan.")
    changed = activity.apply_changes(session, m, changes, "milestone", m.project_id, EDITABLE)
    session.flush()
    return changed


def delete(session: Session, m: Milestone) -> None:
    activity.log(session, "milestone", m.id, "delete", m.project_id, "name", m.name, None)
    session.delete(m)
    session.flush()
