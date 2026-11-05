"""Registar projekta: rizici i problemi, zainteresovane strane, dokumenta i linkovi, odluke.

Sve četiri vrste stavki rade isto: lista po projektu, dodavanje, izmena i brisanje, a svaka
izmena se upisuje u istoriju (activity_log) kao i za zadatke.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Decision,
    DecisionStatus,
    DocStatus,
    ProjectDocument,
    Risk,
    RiskKind,
    RiskStatus,
    Stakeholder,
    Task,
)
from app.services import activity


@dataclass(frozen=True)
class Kind:
    model: type
    entity: str  # naziv u istoriji izmena
    title_field: str
    fields: frozenset[str]
    required: str  # poruka kad naziv nedostaje


RISK = Kind(
    Risk,
    "risk",
    "title",
    frozenset(
        {
            "kind",
            "title",
            "description",
            "probability",
            "impact",
            "status",
            "owner",
            "mitigation",
            "due_date",
            "task_id",
        }
    ),
    "Unesi naziv rizika ili problema.",
)
STAKEHOLDER = Kind(
    Stakeholder,
    "stakeholder",
    "name",
    frozenset(
        {"name", "organization", "role", "raci", "influence", "interest", "email", "phone", "notes"}
    ),
    "Unesi ime osobe ili naziv tima.",
)
DOCUMENT = Kind(
    ProjectDocument,
    "document",
    "title",
    frozenset(
        {"title", "kind", "location", "version", "status", "owner", "doc_date", "notes", "task_id"}
    ),
    "Unesi naziv dokumenta.",
)
DECISION = Kind(
    Decision,
    "decision",
    "title",
    frozenset({"decided_on", "title", "decision", "rationale", "approved_by", "status", "task_id"}),
    "Unesi kratak naziv odluke.",
)

KINDS = {k.entity: k for k in (RISK, STAKEHOLDER, DOCUMENT, DECISION)}

OPEN_RISK = (RiskStatus.OPEN, RiskStatus.IN_PROGRESS)


def _clean(kind: Kind, session: Session, project_id: str, values: dict[str, Any]) -> dict:
    unknown = set(values) - kind.fields
    if unknown:
        raise ValueError(f"Nepoznata polja: {', '.join(sorted(unknown))}")
    out = {}
    for key, value in values.items():
        if isinstance(value, str) and key not in (
            "description",
            "mitigation",
            "notes",
            "decision",
            "rationale",
            "location",
        ):
            value = " ".join(value.split())
        elif isinstance(value, str):
            value = value.strip()
        out[key] = value
    if kind.title_field in out and not out[kind.title_field]:
        raise ValueError(kind.required)
    for key in ("probability", "impact"):
        if key in out and not 1 <= int(out[key]) <= 4:
            raise ValueError("Verovatnoća i uticaj su od 1 do 4.")
    for key in ("influence", "interest"):
        if key in out and not 1 <= int(out[key]) <= 3:
            raise ValueError("Uticaj i interes su od 1 do 3.")
    if "raci" in out:
        out["raci"] = (out["raci"] or "I").upper()
        if out["raci"] not in ("R", "A", "C", "I"):
            raise ValueError("RACI je jedno od: R, A, C, I.")
    if out.get("task_id"):
        task = session.get(Task, out["task_id"])
        if task is None or task.project_id != project_id:
            raise ValueError("Izabrani zadatak ne pripada ovom projektu.")
    elif "task_id" in out:
        out["task_id"] = None
    if "location" in out and len(out["location"]) > 1000:
        raise ValueError("Putanja ili link je predugačak.")
    return out


def create(session: Session, kind: Kind, project_id: str, /, **values: Any) -> Any:
    if kind.title_field not in values:
        raise ValueError(kind.required)
    if kind is DECISION:
        values.setdefault("decided_on", date.today())
    values = _clean(kind, session, project_id, values)
    obj = kind.model(project_id=project_id, **values)
    session.add(obj)
    session.flush()
    activity.log(
        session,
        kind.entity,
        obj.id,
        "create",
        project_id,
        kind.title_field,
        None,
        getattr(obj, kind.title_field),
    )
    return obj


def update(session: Session, kind: Kind, obj: Any, /, **changes: Any) -> list[str]:
    changes = _clean(kind, session, obj.project_id, changes)
    changed = activity.apply_changes(
        session, obj, changes, kind.entity, obj.project_id, kind.fields
    )
    session.flush()
    return changed


def delete(session: Session, kind: Kind, obj: Any) -> None:
    activity.log(
        session,
        kind.entity,
        obj.id,
        "delete",
        obj.project_id,
        kind.title_field,
        getattr(obj, kind.title_field),
        None,
    )
    session.delete(obj)
    session.flush()


def get(session: Session, kind: Kind, item_id: str) -> Any:
    obj = session.get(kind.model, item_id)
    if obj is None:
        raise ValueError("Stavka više ne postoji.")
    return obj


# --- liste ---------------------------------------------------------------------------------------


def risks(session: Session, project_id: str, include_closed: bool = True) -> list[Risk]:
    stmt = select(Risk).where(Risk.project_id == project_id)
    if not include_closed:
        stmt = stmt.where(Risk.status.in_(OPEN_RISK))
    rows = list(session.scalars(stmt))
    # otvoreni pre zatvorenih, pa po oceni (verovatnoća × uticaj), pa po roku
    rows.sort(
        key=lambda r: (
            r.status not in OPEN_RISK,
            -r.score,
            r.due_date or date.max,
            r.title.casefold(),
        )
    )
    return rows


def stakeholders(session: Session, project_id: str) -> list[Stakeholder]:
    order = {"A": 0, "R": 1, "C": 2, "I": 3}
    rows = list(session.scalars(select(Stakeholder).where(Stakeholder.project_id == project_id)))
    rows.sort(key=lambda s: (order.get(s.raci, 9), -s.influence, s.name.casefold()))
    return rows


def documents(session: Session, project_id: str) -> list[ProjectDocument]:
    rows = list(
        session.scalars(select(ProjectDocument).where(ProjectDocument.project_id == project_id))
    )
    rows.sort(key=lambda d: (d.status == DocStatus.OBSOLETE, d.kind.casefold(), d.title))
    return rows


def decisions(session: Session, project_id: str) -> list[Decision]:
    return list(
        session.scalars(
            select(Decision)
            .where(Decision.project_id == project_id)
            .order_by(Decision.decided_on.desc(), Decision.created_at.desc())
        )
    )


@dataclass
class Summary:
    open_risks: int = 0
    critical_risks: int = 0  # otvoreni sa ocenom 12 ili više
    open_issues: int = 0
    stakeholders: int = 0
    documents: int = 0
    decisions: int = 0


def summary(session: Session, project_id: str) -> Summary:
    out = Summary()
    for r in risks(session, project_id, include_closed=False):
        if r.kind == RiskKind.ISSUE:
            out.open_issues += 1
        else:
            out.open_risks += 1
        if r.score >= 12:
            out.critical_risks += 1
    out.stakeholders = len(stakeholders(session, project_id))
    out.documents = len(documents(session, project_id))
    out.decisions = len(decisions(session, project_id))
    return out


__all__ = [
    "DECISION",
    "DOCUMENT",
    "KINDS",
    "RISK",
    "STAKEHOLDER",
    "DecisionStatus",
    "DocStatus",
    "RiskKind",
    "RiskStatus",
]
