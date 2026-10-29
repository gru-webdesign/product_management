"""Puni bazu demo projektom za ručno testiranje.

Pokretanje (demo baza u folderu .data, ne dira pravu bazu):
    Windows PowerShell:  $env:ETAPA_DATA_DIR=".data"; python scripts/seed_demo.py
    ili u VS Code: Run and Debug → "Demo podaci: napuni .data bazu"

Ponovno pokretanje briše i iznova pravi samo demo projekat.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models import (  # noqa: E402
    Budget,
    BudgetCategory,
    DependencyType,
    Milestone,
    Note,
    Priority,
    Project,
    ProjectStatus,
    Tag,
    Task,
    TaskDependency,
    TaskStatus,
)
from app.services.money import to_minor  # noqa: E402

DEMO_NAME = "Redizajn sajta (demo)"


def seed(session: Session, today: date | None = None) -> Project:
    today = today or date.today()
    old = session.scalar(select(Project).where(Project.name == DEMO_NAME))
    if old is not None:
        session.delete(old)
        session.flush()

    def d(offset: int) -> date:
        return today + timedelta(days=offset)

    project = Project(
        name=DEMO_NAME,
        description="Primer projekta sa zadacima, zavisnostima, milestone-ima i budžetom.",
        client="Picerija Primer",
        color="#2F55D4",
        start_date=d(-10),
        end_date=d(35),
        status=ProjectStatus.ACTIVE,
    )
    session.add(project)

    tag_names = {"dizajn": "#7A5AC0", "razvoj": "#2F55D4", "klijent": "#B8620A"}
    tags = {}
    for name, color in tag_names.items():
        tag = session.scalar(select(Tag).where(Tag.name == name)) or Tag(name=name, color=color)
        session.add(tag)
        tags[name] = tag

    def task(
        title,
        start,
        end,
        status=TaskStatus.TODO,
        progress=0,
        prio=Priority.MEDIUM,
        est=None,
        cost=0,
        tag=None,
        parent=None,
        order=0,
    ):
        t = Task(
            project=project,
            parent=parent,
            title=title,
            status=status,
            priority=prio,
            start_date=d(start),
            due_date=d(end),
            progress=progress,
            estimate_hours=est,
            planned_cost_minor=to_minor(cost),
            sort_order=order,
        )
        if tag:
            t.tags.append(tags[tag])
        session.add(t)
        return t

    brief = task(
        "Brief i prikupljanje sadržaja",
        -10,
        -6,
        TaskStatus.DONE,
        100,
        est=6,
        tag="klijent",
        order=0,
    )
    wire = task(
        "Wireframe glavnih stranica",
        -5,
        -1,
        TaskStatus.DONE,
        100,
        Priority.HIGH,
        12,
        tag="dizajn",
        order=1,
    )
    design = task(
        "Vizuelni dizajn",
        0,
        7,
        TaskStatus.IN_PROGRESS,
        40,
        Priority.HIGH,
        24,
        cost=15000,
        tag="dizajn",
        order=2,
    )
    task("Početna stranica", 0, 3, TaskStatus.IN_PROGRESS, 70, est=10, parent=design, order=0)
    task("Meni i cenovnik", 3, 7, TaskStatus.TODO, 0, est=8, parent=design, order=1)
    review = task(
        "Odobrenje klijenta", 8, 9, TaskStatus.TODO, 0, Priority.URGENT, 2, tag="klijent", order=3
    )
    dev = task(
        "Izrada sajta",
        10,
        24,
        TaskStatus.TODO,
        0,
        Priority.HIGH,
        40,
        cost=8000,
        tag="razvoj",
        order=4,
    )
    content = task(
        "Fotografije i tekstovi",
        10,
        18,
        TaskStatus.TODO,
        0,
        est=10,
        cost=20000,
        tag="klijent",
        order=5,
    )
    qa = task("Testiranje na telefonima", 25, 28, TaskStatus.TODO, 0, est=6, tag="razvoj", order=6)
    launch = task("Objava i obuka", 29, 31, TaskStatus.TODO, 0, Priority.HIGH, 4, order=7)
    session.flush()

    for pred, succ in [
        (brief, wire),
        (wire, design),
        (design, review),
        (review, dev),
        (review, content),
        (dev, qa),
        (content, qa),
        (qa, launch),
    ]:
        session.add(
            TaskDependency(predecessor=pred, successor=succ, type=DependencyType.FINISH_TO_START)
        )

    session.add_all(
        [
            Milestone(project=project, name="Dizajn odobren", date=d(9)),
            Milestone(project=project, name="Sajt objavljen", date=d(31)),
            Note(task=design, text="Klijent želi toplije boje i veće fotografije pica."),
        ]
    )

    categories = {c.name: c for c in session.scalars(select(BudgetCategory))}
    plan = {"Rad": 180000, "Materijal": 25000, "Softver i licence": 12000, "Ostalo": 5000}
    for name, amount in plan.items():
        if name in categories:
            session.add(
                Budget(project=project, category=categories[name], planned_minor=to_minor(amount))
            )

    from app.services import budget as budget_service

    def cost(day, amount, category, vendor, currency="RSD", rate="1", t=None, note=""):
        budget_service.add_cost(
            session,
            project.id,
            on=d(day),
            amount_minor=to_minor(amount),
            category_id=categories[category].id,
            currency=currency,
            rate=Decimal(rate),
            task_id=t.id if t else None,
            vendor=vendor,
            note=note,
        )

    cost(-8, 45000, "Rad", "Sopstveni rad", t=brief, note="Sastanci i brief")
    cost(-2, 60000, "Rad", "Sopstveni rad", t=wire)
    cost(
        -1, 89, "Softver i licence", "Figma", currency="EUR", rate="117.2", note="Godišnja licenca"
    )
    cost(1, 9500, "Materijal", "Foto banka", t=content)
    budget_service.add_income(
        session, project.id, on=d(-9), amount_minor=to_minor(120000), description="Avans 50%"
    )
    session.flush()
    return project


def main() -> int:
    from app.main import bootstrap

    db = bootstrap()
    with db.session() as s:
        project = seed(s)
        s.commit()
        print(f"Demo projekat napravljen: {project.name} ({len(project.tasks)} zadataka)")
        print(f"Baza: {db.paths.db_path}")
    db.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
