"""Pregled svih projekata: stanje, budžet, sledeći milestone, rokovi i vreme ove nedelje."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Milestone, Project, Task, TaskStatus
from app.services import budget as budget_service
from app.services import projects as project_service
from app.services import sharing
from app.services import timetracking as tt


@dataclass
class ProjectCard:
    id: str
    name: str
    client: str
    color: str
    done: int
    total: int
    progress: int
    overdue: int
    budget_state: str  # ok / warn / over / unplanned
    budget_percent: int
    has_budget: bool
    next_milestone: str
    next_milestone_date: date | None
    unread: int
    end_date: date | None


@dataclass
class Deadline:
    task_id: str
    project_id: str
    project_name: str
    project_color: str
    title: str
    due: date
    days: int  # negativno = kasni

    @property
    def overdue(self) -> bool:
        return self.days < 0


@dataclass
class Overview:
    today: date
    projects: list[ProjectCard] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)
    week_hours: list[tuple[str, str, str, float]] = field(default_factory=list)

    @property
    def open_tasks(self) -> int:
        return sum(p.total - p.done for p in self.projects)

    @property
    def overdue_tasks(self) -> int:
        return sum(p.overdue for p in self.projects)

    @property
    def hours_this_week(self) -> float:
        return sum(h for *_, h in self.week_hours)


def build(session: Session, today: date | None = None, horizon_days: int = 14) -> Overview:
    today = today or date.today()
    ov = Overview(today=today)
    active = [p for p in project_service.list_projects(session) if not p.archived]
    for p in active:
        done, total, pct = project_service.progress(session, p.id)
        overdue = len(
            list(
                session.scalars(
                    select(Task.id).where(
                        Task.project_id == p.id,
                        Task.due_date < today,
                        Task.status != TaskStatus.DONE,
                    )
                )
            )
        )
        summ = budget_service.summary(session, p.id)
        ms = session.scalar(
            select(Milestone)
            .where(Milestone.project_id == p.id, Milestone.done.is_(False), Milestone.date >= today)
            .order_by(Milestone.date)
            .limit(1)
        )
        ov.projects.append(
            ProjectCard(
                id=p.id,
                name=p.name,
                client=p.client,
                color=p.color,
                done=done,
                total=total,
                progress=pct,
                overdue=overdue,
                budget_state=summ.state,
                budget_percent=summ.percent,
                has_budget=summ.planned > 0,
                next_milestone=ms.name if ms else "",
                next_milestone_date=ms.date if ms else None,
                unread=sharing.unread_count(session, p.id),
                end_date=p.end_date,
            )
        )

    ids = {p.id: p for p in active}
    rows = session.execute(
        select(Task, Project)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.project_id.in_(ids),
            Task.due_date.is_not(None),
            Task.due_date <= today + timedelta(days=horizon_days),
            Task.status != TaskStatus.DONE,
        )
        .order_by(Task.due_date)
    ).all()
    ov.deadlines = [
        Deadline(t.id, p.id, p.name, p.color, t.title, t.due_date, (t.due_date - today).days)
        for t, p in rows
    ]
    monday = tt.week_start(today)
    ov.week_hours = tt.hours_by_project(session, monday, monday + timedelta(days=6))
    return ov


def relative_day(days: int) -> str:
    if days == 0:
        return "danas"
    if days == 1:
        return "sutra"
    if days == -1:
        return "juče"
    if days < 0:
        return f"kasni {-days} d"
    return f"za {days} d"
