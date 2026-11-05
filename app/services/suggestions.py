"""Predlozi za polja sa proizvoljnim unosom: ugrađena lista + ono što je korisnik već upisao."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import labels
from app.db.models import Project, ProjectDocument, Risk, Stakeholder, Task

# polje → (kolone iz kojih se skupljaju upisane vrednosti, ugrađeni predlozi)
SOURCES = {
    "project_type": ([Project.project_type], labels.PROJECT_TYPES),
    "work_type": ([Task.work_type], labels.WORK_TYPES),
    "phase": ([Task.phase], labels.PHASES),
    # ljudi i timovi: nosilac zadatka, nosilac rizika, odeljenje, sponzor, vođa projekta...
    "people": (
        [
            Task.owner,
            Risk.owner,
            ProjectDocument.owner,
            Project.department,
            Project.sponsor,
            Project.manager,
            Stakeholder.name,
        ],
        labels.TEAMS,
    ),
    "doc_kind": ([ProjectDocument.kind], labels.DOC_KINDS),
    "organization": ([Stakeholder.organization, Project.client], labels.ORGANIZATIONS),
    "client": ([Project.client], []),
}


def for_field(session: Session, field: str) -> list[str]:
    """Ugrađeni predlozi pa upisane vrednosti koje nisu među njima, abecedno."""
    columns, builtin = SOURCES[field]
    used: set[str] = set()
    for column in columns:
        used.update(v for v in session.scalars(select(column).distinct()) if v and v.strip())
    extra = sorted(used - set(builtin), key=str.casefold)
    return [*builtin, *extra]
