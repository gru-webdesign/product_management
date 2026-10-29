"""Šabloni projekata: ugrađeni (u kodu) i sačuvani iz postojećih projekata (u bazi).

Format šablona (JSON):
    {"tasks": [{"title", "offset", "days", "estimate", "priority", "parent", "tags"}],
     "deps": [[pred_index, succ_index], ...],
     "milestones": [{"name", "offset"}],
     "budget": {"Naziv kategorije": iznos_u_parama}}
offset = broj dana od početka projekta, days = trajanje u danima, parent = indeks roditelja.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Priority, ProjectTemplate
from app.services import budget as budget_service
from app.services import dependencies as dep_service
from app.services import milestones as ms_service
from app.services import projects as project_service
from app.services import tasks as task_service
from app.services.money import to_minor


@dataclass
class TemplateInfo:
    id: str  # "builtin:<ključ>" ili UUID sačuvanog šablona
    name: str
    description: str
    builtin: bool
    task_count: int


def _t(title, offset, days, estimate=None, priority="medium", parent=None, tags=()):
    return {
        "title": title,
        "offset": offset,
        "days": days,
        "estimate": estimate,
        "priority": priority,
        "parent": parent,
        "tags": list(tags),
    }


BUILTIN: dict[str, dict] = {
    "sajt": {
        "name": "Izrada sajta",
        "description": "Od briefa do objave: dizajn, izrada, sadržaj, testiranje.",
        "data": {
            "tasks": [
                _t("Brief i prikupljanje sadržaja", 0, 4, 6, "medium", tags=["klijent"]),
                _t("Struktura i wireframe", 4, 4, 10, "high", tags=["dizajn"]),
                _t("Vizuelni dizajn", 8, 7, 24, "high", tags=["dizajn"]),
                _t("Početna stranica", 8, 4, 10, parent=2),
                _t("Unutrašnje stranice", 12, 3, 10, parent=2),
                _t("Odobrenje dizajna", 15, 2, 2, "urgent", tags=["klijent"]),
                _t("Izrada sajta", 17, 12, 40, "high", tags=["razvoj"]),
                _t("Tekstovi i fotografije", 17, 8, 10, tags=["klijent"]),
                _t("Testiranje na telefonima i browserima", 29, 3, 6, tags=["razvoj"]),
                _t("Objava i podešavanje domena", 32, 2, 4, "high", tags=["razvoj"]),
            ],
            "deps": [[0, 1], [1, 2], [2, 5], [5, 6], [5, 7], [6, 8], [7, 8], [8, 9]],
            "milestones": [
                {"name": "Dizajn odobren", "offset": 16},
                {"name": "Sajt objavljen", "offset": 33},
            ],
            "budget": {
                "Rad": to_minor(180000),
                "Softver i licence": to_minor(12000),
                "Ostalo": to_minor(5000),
            },
        },
    },
    "redizajn": {
        "name": "Redizajn postojećeg sajta",
        "description": "Analiza starog sajta, novi dizajn, prenos sadržaja i preusmerenja.",
        "data": {
            "tasks": [
                _t("Analiza postojećeg sajta i statistike", 0, 3, 6, tags=["analiza"]),
                _t("Lista stranica i preusmerenja (SEO)", 3, 2, 4, "high", tags=["seo"]),
                _t("Novi dizajn", 5, 7, 20, "high", tags=["dizajn"]),
                _t("Odobrenje klijenta", 12, 2, 2, "urgent", tags=["klijent"]),
                _t("Izrada i prenos sadržaja", 14, 10, 32, "high", tags=["razvoj"]),
                _t("Provera preusmerenja i brzine", 24, 2, 4, tags=["seo"]),
                _t("Objava", 26, 1, 3, "high"),
            ],
            "deps": [[0, 1], [0, 2], [2, 3], [3, 4], [1, 5], [4, 5], [5, 6]],
            "milestones": [{"name": "Novi sajt objavljen", "offset": 26}],
            "budget": {"Rad": to_minor(140000), "Ostalo": to_minor(5000)},
        },
    },
    "kampanja": {
        "name": "Kampanja na društvenim mrežama",
        "description": "Plan, sadržaj, objave i izveštaj za mesečnu kampanju.",
        "data": {
            "tasks": [
                _t("Cilj, publika i budžet kampanje", 0, 2, 3, "high"),
                _t("Plan objava", 2, 3, 4, tags=["sadržaj"]),
                _t("Izrada vizuala i tekstova", 5, 6, 16, "high", tags=["sadržaj"]),
                _t("Odobrenje klijenta", 11, 1, 1, "urgent", tags=["klijent"]),
                _t("Objave i oglasi", 12, 14, 10, tags=["oglasi"]),
                _t("Izveštaj o rezultatima", 26, 2, 3),
            ],
            "deps": [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5]],
            "milestones": [{"name": "Kampanja počinje", "offset": 12}],
            "budget": {"Rad": to_minor(60000), "Ostalo": to_minor(30000)},
        },
    },
}


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
    return {"tasks": tasks, "deps": deps, "milestones": milestones, "budget": budget}


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
    session.flush()
    return len(created)
