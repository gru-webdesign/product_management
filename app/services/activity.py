"""Istorija izmena: ko je šta promenio i kada (jedan korisnik, pa samo šta i kada)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActivityLog
from app.labels import display_value


def log(
    session: Session,
    entity: str,
    entity_id: str,
    action: str,
    project_id: str | None = None,
    field: str = "",
    old: Any = None,
    new: Any = None,
) -> ActivityLog:
    entry = ActivityLog(
        entity=entity,
        entity_id=entity_id,
        project_id=project_id,
        action=action,
        field=field,
        old_value=display_value(field, old) if field else "",
        new_value=display_value(field, new) if field else "",
    )
    session.add(entry)
    return entry


def apply_changes(
    session: Session,
    obj: Any,
    changes: dict[str, Any],
    entity: str,
    project_id: str | None,
    allowed: Iterable[str],
) -> list[str]:
    """Postavlja polja i upisuje svaku stvarnu izmenu u istoriju. Vraća listu promenjenih polja."""
    allowed = set(allowed)
    changed = []
    for field, new in changes.items():
        if field not in allowed:
            raise ValueError(f"Polje '{field}' ne može da se menja")
        old = getattr(obj, field)
        if old == new:
            continue
        setattr(obj, field, new)
        changed.append(field)
        log(session, entity, obj.id, "update", project_id, field, old, new)
    return changed


def history(session: Session, entity_id: str, limit: int = 200) -> list[ActivityLog]:
    stmt = (
        select(ActivityLog)
        .where(ActivityLog.entity_id == entity_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def project_history(session: Session, project_id: str, limit: int = 200) -> list[ActivityLog]:
    stmt = (
        select(ActivityLog)
        .where(ActivityLog.project_id == project_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))
