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

DEMO_NAME = "Onboarding partnera AlfaPay (demo)"
EXTRA_NAME = "Plaćanje računa u TNapp (demo)"
# demo projekti iz ranijih verzija: brišu se pri novom pravljenju demoa
LEGACY_NAMES = ("Redizajn sajta (demo)", "Redizajn sajta — demo")


def seed(session: Session, today: date | None = None) -> Project:
    """Demo projekat: onboarding novog partnera za slanje novca (izmišljen partner AlfaPay)."""
    today = today or date.today()
    for old in session.scalars(select(Project).where(Project.name.in_((DEMO_NAME, *LEGACY_NAMES)))):
        session.delete(old)
    session.flush()

    def d(offset: int) -> date:
        return today + timedelta(days=offset)

    project = Project(
        name=DEMO_NAME,
        description=(
            "Uvođenje partnera AlfaPay za slanje i prijem novca: due diligence i AML, ugovor, "
            "tehnička integracija, UAT i puštanje u rad. Cilj: go-live za 6 nedelja."
        ),
        client="AlfaPay d.o.o.",
        project_type="Onboarding partnera",
        sponsor="Uprava",
        manager="Product",
        department="Product",
        color="#2F55D4",
        start_date=d(-10),
        end_date=d(35),
        status=ProjectStatus.ACTIVE,
    )
    session.add(project)

    tag_names = {"partner": "#B8620A", "aml": "#7A5AC0", "integracija": "#2F55D4"}
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
        owner="",
        phase="",
        work="",
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
            owner=owner,
            phase=phase or (parent.phase if parent else ""),
            work_type=work,
        )
        if tag:
            t.tags.append(tags[tag])
        session.add(t)
        return t

    brief = task(
        "Početni sastanak i obim saradnje",
        -10,
        -6,
        TaskStatus.DONE,
        100,
        est=6,
        tag="partner",
        order=0,
        owner="Product",
        phase="Inicijacija",
        work="Sastanak",
    )
    wire = task(
        "KYB dokumentacija partnera",
        -5,
        -1,
        TaskStatus.DONE,
        100,
        Priority.HIGH,
        12,
        tag="aml",
        order=1,
        owner="Compliance",
        phase="Discovery i analiza",
        work="AML i KYC",
    )
    design = task(
        "AML procena rizika partnera",
        0,
        7,
        TaskStatus.IN_PROGRESS,
        40,
        Priority.HIGH,
        24,
        cost=15000,
        tag="aml",
        order=2,
        owner="AML",
        phase="Discovery i analiza",
        work="AML i KYC",
    )
    task(
        "Provera stvarnih vlasnika",
        0,
        3,
        TaskStatus.IN_PROGRESS,
        70,
        est=10,
        parent=design,
        order=0,
        owner="AML",
        work="AML i KYC",
    )
    task(
        "Provera sankcionih lista",
        3,
        7,
        TaskStatus.BLOCKED,
        0,
        est=8,
        parent=design,
        order=1,
        owner="AML",
        work="AML i KYC",
    )
    review = task(
        "Odobrenje Compliance-a",
        8,
        9,
        TaskStatus.TODO,
        0,
        Priority.URGENT,
        2,
        tag="aml",
        order=3,
        owner="Compliance",
        phase="Discovery i analiza",
        work="Odobrenje",
    )
    dev = task(
        "Razvoj integracije",
        10,
        24,
        TaskStatus.TODO,
        0,
        Priority.HIGH,
        40,
        cost=8000,
        tag="integracija",
        order=4,
        owner="Backend",
        phase="Razvoj i integracija",
        work="Integracija",
    )
    content = task(
        "Ugovor o saradnji i SLA",
        10,
        18,
        TaskStatus.TODO,
        0,
        est=10,
        cost=20000,
        tag="partner",
        order=5,
        owner="Pravna služba",
        phase="Ugovaranje",
        work="Pravno i ugovori",
    )
    qa = task(
        "UAT sa partnerom",
        25,
        28,
        TaskStatus.TODO,
        0,
        est=6,
        tag="integracija",
        order=6,
        owner="QA",
        phase="Testiranje",
        work="UAT",
    )
    launch = task(
        "Go-live",
        29,
        31,
        TaskStatus.TODO,
        0,
        Priority.HIGH,
        4,
        order=7,
        owner="IT razvoj",
        phase="Puštanje u rad",
        work="Puštanje u rad",
    )
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
            Milestone(project=project, name="Compliance odobrio", date=d(9)),
            Milestone(project=project, name="Go-live", date=d(31)),
            Note(task=design, text="Partner je poslao ažuriranu vlasničku strukturu 3.11."),
        ]
    )

    categories = {c.name: c for c in session.scalars(select(BudgetCategory))}
    plan = {
        "Interni rad": 180000,
        "Pravne usluge": 25000,
        "Softver i licence": 12000,
        "Ostalo": 5000,
    }
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

    cost(-8, 45000, "Interni rad", "Interni rad", t=brief, note="Sastanci i analiza")
    cost(-2, 60000, "Interni rad", "Interni rad", t=wire)
    cost(
        -1,
        89,
        "Softver i licence",
        "Atlassian",
        currency="EUR",
        rate="117.2",
        note="Jira i Confluence, mesečno",
    )
    cost(1, 9500, "Pravne usluge", "Advokatska kancelarija", t=content)
    from app.services import timetracking as tt

    for task_obj, day, hours, note in (
        (brief, -9, 3.0, "Sastanak sa partnerom"),
        (brief, -7, 2.5, "Zapisnik i obim saradnje"),
        (wire, -4, 5.5, "Pregled KYB dokumenata"),
        (wire, -2, 4.0, "Dopuna dokumentacije"),
        (design, 0, 3.25, "Upitnik o riziku"),
    ):
        tt.add_entry(session, task_obj.id, d(day), hours, note)
    budget_service.add_income(
        session,
        project.id,
        on=d(-9),
        amount_minor=to_minor(120000),
        description="Naknada za priključenje partnera",
    )
    session.flush()
    _demo_registry(session, project, d, design, review, dev, content)
    _demo_activity(session, project, brief, wire, design, content)
    session.flush()
    return project


def _demo_registry(session: Session, project: Project, d, aml, approval, dev, contract) -> None:
    from app.db.models import DecisionStatus, DocStatus, RiskKind, RiskStatus
    from app.services import registry

    pid = project.id
    for kind, title, p, i, status, owner, mitigation, due, task_obj in (
        (
            RiskKind.RISK,
            "Partner kasni sa dokumentacijom o stvarnim vlasnicima",
            3,
            3,
            RiskStatus.IN_PROGRESS,
            "Compliance",
            "Nedeljni podsetnik; eskalacija na direktora partnera posle 5 dana.",
            d(4),
            aml,
        ),
        (
            RiskKind.ISSUE,
            "Sankcione liste: moguće podudaranje imena jednog direktora",
            2,
            4,
            RiskStatus.OPEN,
            "AML",
            "Tražiti datum rođenja i pasoš radi isključenja.",
            d(2),
            aml,
        ),
        (
            RiskKind.RISK,
            "Kašnjenje API dokumentacije i test okruženja partnera",
            3,
            3,
            RiskStatus.OPEN,
            "IT razvoj",
            "Mock servis za razvoj; rok u ugovoru.",
            d(10),
            dev,
        ),
        (
            RiskKind.DEPENDENCY,
            "Obaveštenje NBS o novom partneru",
            2,
            4,
            RiskStatus.OPEN,
            "Compliance",
            "Proveriti obavezu i rok sa pravnom službom.",
            d(12),
            approval,
        ),
        (
            RiskKind.ASSUMPTION,
            "Partner podržava isplatu u RSD i EUR",
            1,
            3,
            RiskStatus.CLOSED,
            "Product",
            "Potvrđeno na početnom sastanku.",
            None,
            None,
        ),
    ):
        registry.create(
            session,
            registry.RISK,
            pid,
            kind=kind,
            title=title,
            probability=p,
            impact=i,
            status=status,
            owner=owner,
            mitigation=mitigation,
            due_date=due,
            task_id=task_obj.id if task_obj else None,
        )
    for name, org, role, raci, infl, inter, email in (
        ("Uprava", "Interno", "Sponzor projekta", "A", 3, 2, ""),
        ("Product", "Interno", "Vođa projekta", "R", 3, 3, ""),
        ("Compliance i AML", "Interno", "Procena i odobrenje partnera", "A", 3, 3, ""),
        ("Pravna služba", "Interno", "Ugovor, NDA i SLA", "C", 2, 2, ""),
        ("IT razvoj", "Interno", "Integracija", "R", 2, 3, ""),
        (
            "Kontakt osoba AlfaPay",
            "Partner",
            "Koordinator onboardinga",
            "C",
            2,
            3,
            "onboarding@alfapay.example",
        ),
        ("Korisnička podrška", "Interno", "Podrška posle puštanja", "I", 1, 2, ""),
    ):
        registry.create(
            session,
            registry.STAKEHOLDER,
            pid,
            name=name,
            organization=org,
            role=role,
            raci=raci,
            influence=infl,
            interest=inter,
            email=email,
        )
    for title, kind, version, status, owner, location, task_obj in (
        (
            "NDA AlfaPay",
            "NDA",
            "1.0",
            DocStatus.APPROVED,
            "Pravna služba",
            "https://intranet.example/pravna/nda-alfapay.pdf",
            None,
        ),
        (
            "KYB dokumentacija AlfaPay",
            "AML/KYC procedura",
            "",
            DocStatus.APPROVED,
            "Compliance",
            "https://intranet.example/compliance/alfapay-kyb",
            None,
        ),
        ("AML procena rizika partnera", "Procena rizika", "0.3", DocStatus.DRAFT, "AML", "", aml),
        (
            "Ugovor o saradnji i SLA",
            "Ugovor",
            "0.2",
            DocStatus.REVIEW,
            "Pravna služba",
            "",
            contract,
        ),
        (
            "Tehnička specifikacija integracije",
            "Tehnička specifikacija",
            "",
            DocStatus.DRAFT,
            "IT razvoj",
            "",
            dev,
        ),
    ):
        registry.create(
            session,
            registry.DOCUMENT,
            pid,
            title=title,
            kind=kind,
            version=version,
            status=status,
            owner=owner,
            location=location,
            task_id=task_obj.id if task_obj else None,
            doc_date=d(-3),
        )
    for day, title, text, why, by, status in (
        (
            -8,
            "Integracija preko REST API-ja partnera",
            "Koristimo REST API partnera za slanje i statuse; fajl razmena samo za poravnanje.",
            "Brže potvrde i manje ručnog rada; partner ne podržava SFTP za statuse.",
            "Product i IT razvoj",
            DecisionStatus.APPROVED,
        ),
        (
            -3,
            "Pilot sa limitom 500.000 RSD dnevno prve dve nedelje",
            "Posle go-live-a dnevni limit za partnera je 500.000 RSD dok se ne prikupi iskustvo.",
            "Smanjuje rizik zloupotrebe dok AML scenariji ne budu potvrđeni u praksi.",
            "Uprava",
            DecisionStatus.PROPOSED,
        ),
    ):
        registry.create(
            session,
            registry.DECISION,
            pid,
            decided_on=d(day),
            title=title,
            decision=text,
            rationale=why,
            approved_by=by,
            status=status,
        )


def _demo_activity(session: Session, project: Project, brief, wire, design, content) -> None:
    """Nekoliko izmena unazad, da Pregled i istorija imaju šta da prikažu."""
    from datetime import UTC, datetime

    from app.services import activity

    now = datetime.now(UTC)
    owners = next(t for t in design.subtasks if t.title == "Provera stvarnih vlasnika")
    for minutes, obj, field, old, new in (
        (60 * 26, brief, "status", TaskStatus.REVIEW, TaskStatus.DONE),
        (60 * 22, wire, "status", TaskStatus.REVIEW, TaskStatus.DONE),
        (60 * 5, design, "status", TaskStatus.TODO, TaskStatus.IN_PROGRESS),
        (95, content, "due_date", None, content.due_date),
        (40, owners, "progress", 40, 70),
        (12, design, "progress", 20, 40),
    ):
        entry = activity.log(session, "task", obj.id, "update", project.id, field, old, new)
        entry.created_at = now - timedelta(minutes=minutes)


def seed_extra(session: Session, today: date | None = None) -> Project:
    """Drugi demo projekat iz šablona „Novi servis u aplikaciji“, da Pregled ima više projekata."""
    from app.services import projects as project_service
    from app.services import tasks as task_service
    from app.services import templates

    today = today or date.today()
    old = session.scalar(select(Project).where(Project.name == EXTRA_NAME))
    if old is not None:
        session.delete(old)
        session.flush()
    start = today - timedelta(days=20)
    project = project_service.create(
        session,
        name=EXTRA_NAME,
        project_type="Novi servis ili proizvod",
        client="Korisnici TNapp",
        sponsor="Uprava",
        manager="Product",
        department="Product",
        color="#0E7C86",
        start_date=start,
        status=ProjectStatus.ACTIVE,
        description="Plaćanje računa (struja, telefon, komunalije) direktno iz aplikacije.",
    )
    templates.apply(session, project.id, templates.get_data(session, "builtin:novi_servis"), start)
    for t, _ in task_service.tree(session, project.id):
        if t.due_date and t.due_date < today - timedelta(days=1):
            task_service.update(session, t, status=TaskStatus.DONE)
        elif t.start_date and t.start_date <= today and not t.subtasks:
            task_service.update(session, t, status=TaskStatus.IN_PROGRESS, progress=50)
    session.flush()
    return project


def main() -> int:
    from app.main import bootstrap

    db = bootstrap()
    with db.session() as s:
        project = seed(s)
        extra = seed_extra(s)
        s.commit()
        for p in (project, extra):
            print(f"Demo projekat napravljen: {p.name} ({len(p.tasks)} zadataka)")
        print(f"Baza: {db.paths.db_path}")
    db.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
