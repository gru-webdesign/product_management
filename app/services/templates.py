"""Šabloni projekata: ugrađeni (u kodu) i sačuvani iz postojećih projekata (u bazi).

Format šablona (JSON):
    {"tasks": [{"title", "offset", "days", "estimate", "priority", "parent", "tags",
                "owner", "work_type", "phase"}],
     "deps": [[pred_index, succ_index], ...],
     "milestones": [{"name", "offset"}],
     "budget": {"Naziv kategorije": iznos_u_parama},
     "risks": [{"kind", "title", "probability", "impact", "owner", "mitigation"}],
     "stakeholders": [{"name", "organization", "role", "raci", "influence", "interest"}],
     "documents": [{"title", "kind", "owner", "status"}]}
offset = broj dana od početka projekta, days = trajanje u danima, parent = indeks roditelja.
Ugrađeni šabloni su u template_library.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocStatus, Priority, ProjectTemplate, RiskKind, RiskStatus
from app.services import budget as budget_service
from app.services import dependencies as dep_service
from app.services import milestones as ms_service
from app.services import projects as project_service
from app.services import registry
from app.services import tasks as task_service


@dataclass
class TemplateInfo:
    id: str  # "builtin:<ključ>" ili UUID sačuvanog šablona
    name: str
    description: str
    builtin: bool
    task_count: int


from app.services.template_library import BUILTIN  # noqa: E402


def list_templates(session: Session) -> list[TemplateInfo]:
    out = [
        TemplateInfo(f"builtin:{k}", v["name"], v["description"], True, len(v["data"]["tasks"]))
        for k, v in BUILTIN.items()
    ]
    for t in session.scalars(select(ProjectTemplate).order_by(ProjectTemplate.name)):
        data = json.loads(t.data)
        out.append(TemplateInfo(t.id, t.name, t.description, False, len(data.get("tasks", []))))
    return out


def get_data(session: Session, template_id: str) -> dict:
    if template_id.startswith("builtin:"):
        key = template_id.split(":", 1)[1]
        if key not in BUILTIN:
            raise ValueError("Šablon ne postoji.")
        return BUILTIN[key]["data"]
    t = session.get(ProjectTemplate, template_id)
    if t is None:
        raise ValueError("Šablon ne postoji.")
    return json.loads(t.data)


def from_project(session: Session, project_id: str) -> dict:
    """Pravi podatke šablona iz projekta (datumi postaju pomeraji od početka)."""
    p = project_service.get(session, project_id)
    tree = task_service.tree(session, project_id)
    dates = [d for t, _ in tree for d in (t.start_date, t.due_date) if d]
    dates += [m.date for m in ms_service.for_project(session, project_id)]
    origin = p.start_date or (min(dates) if dates else date.today())
    index = {t.id: i for i, (t, _) in enumerate(tree)}
    tasks = []
    for t, _ in tree:
        start = t.start_date or t.due_date
        end = t.due_date or t.start_date
        tasks.append(
            {
                "title": t.title,
                "offset": (start - origin).days if start else None,
                "days": (end - start).days + 1 if start and end else None,
                "estimate": t.estimate_hours,
                "priority": t.priority.value,
                "parent": index.get(t.parent_id),
                "tags": sorted(g.name for g in t.tags),
                "owner": t.owner,
                "work_type": t.work_type,
                "phase": t.phase,
            }
        )
    deps = [
        [index[d.predecessor_id], index[d.successor_id]]
        for d in dep_service.for_project(session, project_id)
        if d.predecessor_id in index and d.successor_id in index
    ]
    milestones = [
        {"name": m.name, "offset": (m.date - origin).days}
        for m in ms_service.for_project(session, project_id)
    ]
    cats = {c.id: c.name for c in budget_service.categories(session)}
    budget = {
        cats[cid]: amount
        for cid, amount in budget_service.planned(session, project_id).items()
        if amount and cid in cats
    }
    risks = [
        {
            "kind": r.kind.value,
            "title": r.title,
            "probability": r.probability,
            "impact": r.impact,
            "owner": r.owner,
            "mitigation": r.mitigation,
        }
        for r in registry.risks(session, project_id)
    ]
    stakeholders = [
        {
            "name": x.name,
            "organization": x.organization,
            "role": x.role,
            "raci": x.raci,
            "influence": x.influence,
            "interest": x.interest,
        }
        for x in registry.stakeholders(session, project_id)
    ]
    documents = [
        {"title": d.title, "kind": d.kind, "owner": d.owner, "status": DocStatus.DRAFT.value}
        for d in registry.documents(session, project_id)
    ]
    return {
        "tasks": tasks,
        "deps": deps,
        "milestones": milestones,
        "budget": budget,
        "risks": risks,
        "stakeholders": stakeholders,
        "documents": documents,
    }


def save_from_project(
    session: Session, project_id: str, name: str, description: str = ""
) -> ProjectTemplate:
    name = name.strip()
    if not name:
        raise ValueError("Unesi naziv šablona.")
    if name.lower() in {v["name"].lower() for v in BUILTIN.values()}:
        raise ValueError("Ugrađeni šablon već ima taj naziv.")
    existing = session.scalar(select(ProjectTemplate).where(ProjectTemplate.name == name))
    data = json.dumps(from_project(session, project_id), ensure_ascii=False)
    if existing:
        existing.data, existing.description = data, description.strip()
        session.flush()
        return existing
    t = ProjectTemplate(name=name, description=description.strip(), data=data)
    session.add(t)
    session.flush()
    return t


def delete(session: Session, template_id: str) -> None:
    if template_id.startswith("builtin:"):
        raise ValueError("Ugrađeni šablon ne može da se obriše.")
    t = session.get(ProjectTemplate, template_id)
    if t is not None:
        session.delete(t)
        session.flush()


def apply(session: Session, project_id: str, data: dict, start: date) -> int:
    """Dodaje zadatke, zavisnosti, milestone-e i budžet iz šablona. Vraća broj zadataka."""
    created = []
    for spec in data.get("tasks", []):
        parent = spec.get("parent")
        offset, days = spec.get("offset"), spec.get("days")
        s = start + timedelta(days=offset) if offset is not None else None
        e = s + timedelta(days=max(1, days or 1) - 1) if s is not None else None
        try:
            priority = Priority(spec.get("priority") or "medium")
        except ValueError:
            priority = Priority.MEDIUM
        task = task_service.create(
            session,
            project_id,
            title=spec["title"],
            start_date=s,
            due_date=e,
            estimate_hours=spec.get("estimate"),
            priority=priority,
            parent_id=created[parent].id if parent is not None and parent < len(created) else None,
            tags=spec.get("tags") or None,
            owner=spec.get("owner") or "",
            work_type=spec.get("work_type") or "",
            phase=spec.get("phase") or "",
        )
        created.append(task)
    for a, b in data.get("deps", []):
        if a < len(created) and b < len(created):
            try:
                dep_service.add(session, created[a], created[b])
            except ValueError:
                pass  # npr. duplikat u ručno izmenjenom šablonu
    for m in data.get("milestones", []):
        ms_service.create(session, project_id, m["name"], start + timedelta(days=m["offset"]))
    cats = {c.name: c.id for c in budget_service.categories(session)}
    for name, amount in data.get("budget", {}).items():
        if name in cats:
            budget_service.set_planned(session, project_id, cats[name], int(amount))
    for kind, key in (
        (registry.RISK, "risks"),
        (registry.STAKEHOLDER, "stakeholders"),
        (registry.DOCUMENT, "documents"),
    ):
        for spec in data.get(key, []):
            values = {k: v for k, v in spec.items() if k in kind.fields and k != "task_id"}
            try:
                registry.create(session, kind, project_id, **_enums(key, values))
            except (ValueError, KeyError):
                pass  # ručno izmenjen šablon sa neispravnom stavkom
    session.flush()
    return len(created)


def _enums(key: str, values: dict) -> dict:
    if key == "risks":
        for field, enum in (("kind", RiskKind), ("status", RiskStatus)):
            if field in values:
                values[field] = enum(values[field])
    if key == "documents" and "status" in values:
        values["status"] = DocStatus(values["status"])
    return values
