"""Nasumične operacije nad servisima i provera da baza ostaje ispravna.

Svaka runda radi stotine izmena (projekti, zadaci, podzadaci, datumi, zavisnosti, vreme,
troškovi, registar, brisanja) i posle svakog commit-a proverava invarijante. Seme je fiksno,
pa je test ponovljiv; ETAPA_FUZZ=<broj> pokreće više rundi lokalno.
"""

from __future__ import annotations

import datetime as dt
import os
import random

import pytest
from sqlalchemy import func, select, text

from app.db.models import (
    ActivityLog,
    CostEntry,
    Project,
    Task,
    TaskDependency,
    TaskStatus,
    TimeEntry,
)
from app.services import budget, dependencies, milestones, projects, registry, tasks, timetracking
from app.services.dependencies import required_shift

D0 = dt.date(2026, 1, 5)
TITLES = ["Analiza", "Razvoj", "UAT", "Go-live", "Ugovor", "Ž č ć đ š 🚀", "x" * 300, "  a  b  "]


def _rand_dates(rng: random.Random):
    if rng.random() < 0.2:
        return None, None
    start = D0 + dt.timedelta(days=rng.randint(0, 200))
    return start, start + dt.timedelta(days=rng.randint(0, 30))


def check_invariants(session) -> None:
    conn = session.connection()
    assert conn.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    for t in session.scalars(select(Task)):
        assert session.get(Project, t.project_id) is not None
        if t.parent_id:
            assert t.parent.project_id == t.project_id, "podzadatak u drugom projektu"
            assert t.id not in tasks.descendant_ids(t), "zadatak je sam sebi predak"
        if t.start_date and t.due_date:
            assert t.due_date >= t.start_date, f"rok pre početka: {t.title}"
        assert 0 <= t.progress <= 100
        assert t.title == t.title.strip() and t.title
        n, total = session.execute(
            select(func.count(TimeEntry.id), func.coalesce(func.sum(TimeEntry.hours), 0)).where(
                TimeEntry.task_id == t.id
            )
        ).one()
        if n:  # bez unosa ostaje ručno upisana vrednost
            assert abs((t.actual_hours or 0) - total) < 0.01, "utrošeno != zbir unosa vremena"
    deps = session.scalars(select(TaskDependency)).all()
    graph: dict[str, set[str]] = {}
    for d in deps:
        assert d.predecessor.project_id == d.successor.project_id
        assert d.predecessor_id != d.successor_id
        assert required_shift(d, d.predecessor, d.successor) == 0, "zavisnost nije ispunjena"
        graph.setdefault(d.predecessor_id, set()).add(d.successor_id)
    # bez krugova
    seen: dict[str, int] = {}

    def visit(n: str) -> None:
        seen[n] = 1
        for m in graph.get(n, ()):
            assert seen.get(m) != 1, "krug u zavisnostima"
            if m not in seen:
                visit(m)
        seen[n] = 2

    for n in list(graph):
        if n not in seen:
            visit(n)
    for c in session.scalars(select(CostEntry)):
        assert isinstance(c.amount_minor, int) and isinstance(c.amount_base_minor, int)
        assert c.amount_minor >= 0
        if c.task_id:
            assert session.get(Task, c.task_id).project_id == c.project_id


def run_round(session, seed: int, steps: int = 400) -> dict[str, int]:
    rng = random.Random(seed)
    stats: dict[str, int] = {}
    cat_id = budget.categories(session)[0].id

    def pick_project():
        ps = session.scalars(select(Project)).all()
        return rng.choice(ps) if ps else None

    def pick_task(project=None):
        q = select(Task)
        if project is not None:
            q = q.where(Task.project_id == project.id)
        ts = session.scalars(q).all()
        return rng.choice(ts) if ts else None

    for step in range(steps):
        op = rng.choice(
            [
                "project", "task", "task", "subtask", "dates", "dates", "status", "dep", "dep",
                "undep", "delete_task", "time", "untime", "cost", "risk", "steps", "move",
                "milestone", "delete_project", "archive", "update_title",
            ]
        )  # fmt: skip
        try:
            if op == "project" or pick_project() is None:
                start, end = _rand_dates(rng)
                projects.create(
                    session, name=f"P{step} {rng.choice(TITLES)}", start_date=start, end_date=end
                )
            elif op == "task":
                p = pick_project()
                start, due = _rand_dates(rng)
                tasks.create(
                    session,
                    p.id,
                    title=rng.choice(TITLES),
                    start_date=start,
                    due_date=due,
                    status=rng.choice(list(TaskStatus)),
                    estimate_hours=rng.choice([None, 0, 1.5, 40]),
                    tags=rng.sample(["a", "b", "TNapp", "č"], rng.randint(0, 2)),
                )
            elif op == "subtask":
                parent = pick_task()
                if parent:
                    tasks.add_steps(session, parent, rng.sample(TITLES, 2))
            elif op == "dates":
                t = pick_task()
                if t:
                    start, due = _rand_dates(rng)
                    tasks.set_dates(session, t, start, due)
            elif op == "move":
                t = pick_task()
                if t:
                    tasks.move_by_days(session, t, rng.randint(-10, 20))
            elif op == "status":
                t = pick_task()
                if t:
                    tasks.update(session, t, status=rng.choice(list(TaskStatus)))
            elif op == "update_title":
                t = pick_task()
                if t:
                    tasks.update(session, t, title=rng.choice(TITLES), progress=rng.randint(0, 100))
            elif op == "dep":
                p = pick_project()
                a, b = pick_task(p), pick_task(p)
                if a and b:
                    dependencies.add(
                        session,
                        a,
                        b,
                        rng.choice(list(dependencies.DependencyType)),
                        rng.randint(-2, 3),
                    )
            elif op == "undep":
                ds = session.scalars(select(TaskDependency)).all()
                if ds:
                    dependencies.remove(session, rng.choice(ds))
            elif op == "delete_task":
                t = pick_task()
                if t:
                    tasks.delete(session, t)
            elif op == "time":
                t = pick_task()
                if t:
                    timetracking.add_entry(
                        session, t.id, D0 + dt.timedelta(days=rng.randint(0, 60)),
                        rng.choice([0.25, 1, 7.5]),
                    )  # fmt: skip
            elif op == "untime":
                es = session.scalars(select(TimeEntry)).all()
                if es:
                    timetracking.delete_entry(session, rng.choice(es))
            elif op == "cost":
                p = pick_project()
                t = pick_task(p) if rng.random() < 0.5 else None
                budget.add_cost(
                    session,
                    p.id,
                    on=D0,
                    amount_minor=rng.randint(0, 10_000_000),
                    category_id=cat_id,
                    currency=rng.choice(["RSD", "EUR"]),
                    rate=rng.choice([1, "117.2"]),
                    task_id=t.id if t else None,
                )
            elif op == "risk":
                p = pick_project()
                t = pick_task(p)
                registry.create(
                    session,
                    registry.RISK,
                    p.id,
                    title=rng.choice(TITLES),
                    probability=rng.randint(1, 4),
                    impact=rng.randint(1, 4),
                    task_id=t.id if t else None,
                )
            elif op == "milestone":
                p = pick_project()
                milestones.create(session, p.id, rng.choice(TITLES), D0)
            elif op == "archive":
                p = pick_project()
                projects.set_archived(session, p, rng.random() < 0.5)
            elif op == "delete_project" and rng.random() < 0.3:
                projects.delete(session, pick_project())
            stats[op] = stats.get(op, 0) + 1
        except ValueError:
            stats["odbijeno"] = stats.get("odbijeno", 0) + 1  # validacija je očekivana
            session.rollback()
            continue
        session.commit()
        if step % 25 == 0:
            check_invariants(session)
    check_invariants(session)
    return stats


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_random_operations_keep_database_consistent(session, seed):
    stats = run_round(session, seed)
    assert stats.get("task", 0) > 20
    created = session.scalar(
        select(func.count()).select_from(ActivityLog).where(ActivityLog.action == "create")
    )
    assert created > 0


@pytest.mark.skipif(not os.environ.get("ETAPA_FUZZ"), reason="duže, samo lokalno")
def test_random_operations_long(session):
    for seed in range(int(os.environ["ETAPA_FUZZ"])):
        run_round(session, 1000 + seed, steps=300)
