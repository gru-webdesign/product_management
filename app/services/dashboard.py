"""Pregled svih projekata: stanje, budžet, sledeći milestone, rokovi i vreme ove nedelje."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ActivityLog, Milestone, Project, Task, TaskStatus, TimeEntry
from app.labels import FIELD
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
class ActivityItem:
    when: datetime
    project_id: str
    project_name: str
    project_color: str
    text: str
    kind: str  # create / update / done / delete


@dataclass
class Overview:
    today: date
    projects: list[ProjectCard] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)
    week_hours: list[tuple[str, str, str, float]] = field(default_factory=list)
    # broj zadataka po statusu u aktivnim projektima
    status_counts: dict[TaskStatus, int] = field(default_factory=dict)
    # sati po danu ove nedelje (ponedeljak..nedelja)
    week_days: list[tuple[date, float]] = field(default_factory=list)
    activity: list[ActivityItem] = field(default_factory=list)

    @property
    def total_tasks(self) -> int:
        return sum(self.status_counts.values())

    @property
    def done_percent(self) -> int:
        total = self.total_tasks
        return round(100 * self.status_counts.get(TaskStatus.DONE, 0) / total) if total else 0

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
    if ids:
        counts = session.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.project_id.in_(ids))
            .group_by(Task.status)
        ).all()
        ov.status_counts = {status: n for status, n in counts}
    by_day = dict(
        session.execute(
            select(TimeEntry.date, func.sum(TimeEntry.hours))
            .where(TimeEntry.date >= monday, TimeEntry.date <= monday + timedelta(days=6))
            .group_by(TimeEntry.date)
        ).all()
    )
    ov.week_days = [
        (monday + timedelta(days=i), float(by_day.get(monday + timedelta(days=i), 0) or 0))
        for i in range(7)
    ]
    ov.activity = activity_feed(session, ids)
    return ov


SHOW_VALUE = ("progress", "due_date", "start_date", "priority", "estimate_hours")


def activity_feed(session: Session, projects: dict[str, Project], limit: int = 7) -> list:
    """Poslednje izmene zadataka i milestone-a, spojene po stavci i trenutku."""
    if not projects:
        return []
    rows = list(
        session.scalars(
            select(ActivityLog)
            .where(
                ActivityLog.project_id.in_(list(projects)),
                ActivityLog.entity.in_(("task", "milestone")),
            )
            .order_by(ActivityLog.created_at.desc())
            .limit(limit * 6)
        )
    )
    task_ids = {r.entity_id for r in rows if r.entity == "task"}
    titles = dict(session.execute(select(Task.id, Task.title).where(Task.id.in_(task_ids))).all())
    ms_ids = {r.entity_id for r in rows if r.entity == "milestone"}
    ms_names = dict(
        session.execute(select(Milestone.id, Milestone.name).where(Milestone.id.in_(ms_ids))).all()
    )
    groups: list[list[ActivityLog]] = []
    for r in rows:
        last = groups[-1][0] if groups else None
        if (
            last is not None
            and last.entity_id == r.entity_id
            and last.action == r.action
            and abs((last.created_at - r.created_at).total_seconds()) < 60
        ):
            groups[-1].append(r)
        else:
            groups.append([r])
    items = []
    for g in groups[:limit]:
        first = g[0]
        p = projects[first.project_id]
        if first.entity == "milestone":
            name = ms_names.get(first.entity_id) or first.old_value
            text, kind = (
                (f"Milestone „{name}“ dodat", "create")
                if first.action == "create"
                else (f"Milestone „{name}“ obrisan", "delete")
                if first.action == "delete"
                else (f"Milestone „{name}“ izmenjen", "update")
            )
        else:
            title = titles.get(first.entity_id) or first.old_value or "zadatak"
            fields = [r.field for r in g if r.field]
            status = next((r for r in g if r.field == "status"), None)
            if first.action == "create":
                text, kind = f"Novi zadatak „{title}“", "create"
            elif first.action == "delete":
                text, kind = f"Obrisan zadatak „{title}“", "delete"
            elif status is not None:
                done = status.new_value.lower().startswith("završ")
                text = f"„{title}“: {status.new_value.lower()}"
                kind = "done" if done else "update"
            elif len(set(fields)) == 1 and fields[0] in SHOW_VALUE:
                label = FIELD.get(fields[0], fields[0])
                text, kind = f"„{title}“: {label} {g[0].new_value}", "update"
            elif fields == ["dependency"]:
                text, kind = f"„{title}“: izmenjena zavisnost", "update"
            else:
                labels = ", ".join(dict.fromkeys(FIELD.get(f, f) for f in fields))
                text, kind = f"„{title}“: {labels}", "update"
        items.append(ActivityItem(first.created_at, p.id, p.name, p.color, text, kind))
    return items


def time_ago(when: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    seconds = (now - when).total_seconds()
    if seconds < 60:
        return "upravo"
    if seconds < 3600:
        return f"pre {int(seconds // 60)} min"
    if seconds < 86400:
        return f"pre {int(seconds // 3600)} h"
    days = int(seconds // 86400)
    return "juče" if days == 1 else f"pre {days} d"


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
