"""Snimak stanja projekta za stranicu za deljenje: samo ono što gledalac sme da vidi.

Snimak ne sadrži beleške, opise zadataka, troškove po dobavljaču ni istoriju izmena.
Budžet ulazi samo ako je to uključeno u podešavanjima linka.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.db.models import TaskStatus
from app.labels import (
    PRIORITY,
    PRIORITY_COLOR,
    PROJECT_STATUS,
    TASK_STATUS,
    TASK_STATUS_COLOR,
)
from app.services import budget as budget_service
from app.services import dependencies as dep_service
from app.services import milestones as ms_service
from app.services import projects as project_service
from app.services import tasks as task_service
from app.services.money import format_money


@dataclass
class ShareOptions:
    show_gantt: bool = True
    show_list: bool = True
    show_budget: bool = False


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def build(
    session: Session, project_id: str, options: ShareOptions, today: date | None = None
) -> dict:
    today = today or date.today()
    p = project_service.get(session, project_id)
    if p is None:
        raise ValueError("Projekat ne postoji.")
    done, total, pct = project_service.progress(session, project_id)
    tree = task_service.tree(session, project_id)
    parents = {t.parent_id for t, _ in tree if t.parent_id}
    tasks = [
        {
            "id": t.id,
            "title": t.title,
            "depth": depth,
            "parent": bool(t.id in parents),
            "status": TASK_STATUS[t.status],
            "status_color": TASK_STATUS_COLOR[t.status],
            "done": t.status == TaskStatus.DONE,
            "priority": PRIORITY[t.priority],
            "priority_color": PRIORITY_COLOR[t.priority],
            "start": _d(t.start_date or t.due_date),
            "end": _d(t.due_date or t.start_date),
            "progress": 100 if t.status == TaskStatus.DONE else t.progress,
            "overdue": task_service.is_overdue(t, today),
        }
        for t, depth in tree
    ]
    ids = {t["id"] for t in tasks}
    deps = [
        {"from": d.predecessor_id, "to": d.successor_id, "type": d.type.value}
        for d in dep_service.for_project(session, project_id)
        if d.predecessor_id in ids and d.successor_id in ids
    ]
    milestones = [
        {"name": m.name, "date": _d(m.date), "done": m.done}
        for m in ms_service.for_project(session, project_id)
    ]
    data = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "project": {
            "name": p.name,
            "client": p.client,
            "color": p.color,
            "status": PROJECT_STATUS[p.status],
            "start": _d(p.start_date),
            "end": _d(p.end_date),
            "done": done,
            "total": total,
            "progress": pct,
        },
        "show": {
            "gantt": options.show_gantt,
            "list": options.show_list,
            "budget": options.show_budget,
        },
        "tasks": tasks,
        "deps": deps if options.show_gantt else [],
        "milestones": milestones,
    }
    if options.show_budget:
        s = budget_service.summary(session, project_id)
        fm = lambda v: format_money(v, s.base)  # noqa: E731
        data["budget"] = {
            "planned": fm(s.planned),
            "spent": fm(s.spent),
            "remaining": fm(s.remaining),
            "percent": s.percent,
            "state": s.state,
            "lines": [
                {
                    "name": line.name,
                    "color": line.color,
                    "planned": fm(line.planned),
                    "spent": fm(line.spent),
                    "percent": line.percent,
                    "state": s.line_state(line),
                }
                for line in s.lines
            ],
        }
    return data
