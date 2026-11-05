"""Registar projekta (rizici, ljudi, dokumenta, odluke), novi statusi i migracija postojeće baze."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date

import pytest
from alembic import command

from app.db.base import Database, alembic_config
from app.db.models import ActivityLog, DecisionStatus, RiskKind, RiskStatus, TaskStatus
from app.services import projects as projects_svc
from app.services import registry, suggestions
from app.services import tasks as tasks_svc

D = date(2026, 11, 5)


@pytest.fixture
def project(session):
    return projects_svc.create(session, name="Onboarding", project_type="Onboarding partnera")


def test_risk_crud_score_order_and_history(session, project):
    low = registry.create(session, registry.RISK, project.id, title="Mali", probability=1, impact=2)
    high = registry.create(
        session,
        registry.RISK,
        project.id,
        title="  Veliki  rizik ",
        probability=4,
        impact=3,
        kind=RiskKind.ISSUE,
        owner=" AML ",
    )
    assert high.title == "Veliki rizik" and high.owner == "AML" and high.score == 12
    assert [r.title for r in registry.risks(session, project.id)] == ["Veliki rizik", "Mali"]
    registry.update(session, registry.RISK, high, status=RiskStatus.CLOSED)
    assert [r.title for r in registry.risks(session, project.id, include_closed=False)] == ["Mali"]
    s = registry.summary(session, project.id)
    assert (s.open_risks, s.open_issues, s.critical_risks) == (1, 0, 0)
    entities = {a.entity for a in session.query(ActivityLog).filter_by(project_id=project.id)}
    assert "risk" in entities
    registry.delete(session, registry.RISK, low)
    assert len(registry.risks(session, project.id)) == 1


def test_validation(session, project):
    with pytest.raises(ValueError):
        registry.create(session, registry.RISK, project.id, title=" ")
    with pytest.raises(ValueError):
        registry.create(session, registry.RISK, project.id, title="x", probability=5)
    with pytest.raises(ValueError):
        registry.create(session, registry.STAKEHOLDER, project.id, name="Ana", raci="X")
    other = projects_svc.create(session, name="Drugi")
    foreign = tasks_svc.create(session, other.id, title="tuđi")
    with pytest.raises(ValueError):
        registry.create(session, registry.DOCUMENT, project.id, title="Ugovor", task_id=foreign.id)


def test_stakeholders_documents_decisions(session, project):
    registry.create(session, registry.STAKEHOLDER, project.id, name="IT", raci="R")
    registry.create(session, registry.STAKEHOLDER, project.id, name="Uprava", raci="a")
    assert [x.name for x in registry.stakeholders(session, project.id)] == ["Uprava", "IT"]
    task = tasks_svc.create(session, project.id, title="Ugovor")
    doc = registry.create(
        session,
        registry.DOCUMENT,
        project.id,
        title="SLA",
        kind="SLA",
        location="https://intranet/sla.pdf",
        task_id=task.id,
    )
    assert doc.task.title == "Ugovor"
    registry.create(session, registry.DECISION, project.id, title="Starija", decided_on=D)
    newer = registry.create(
        session,
        registry.DECISION,
        project.id,
        title="Novija",
        decided_on=date(2026, 11, 6),
        status=DecisionStatus.PROPOSED,
    )
    assert registry.decisions(session, project.id)[0].id == newer.id
    tasks_svc.delete(session, task)
    session.expire_all()
    assert registry.documents(session, project.id)[0].task_id is None  # veza se samo skida


def test_project_delete_removes_registry(session, project):
    registry.create(session, registry.RISK, project.id, title="R")
    registry.create(session, registry.DECISION, project.id, title="O")
    projects_svc.delete(session, project)
    session.flush()
    assert registry.risks(session, project.id) == []


def test_new_statuses_and_suggestions(session, project):
    t = tasks_svc.create(
        session,
        project.id,
        title="Čeka partnera",
        status=TaskStatus.BLOCKED,
        owner=" Pravna  služba ",
        phase="Ugovaranje",
        work_type="Moj tip",
    )
    assert t.owner == "Pravna služba"
    tasks_svc.update(session, t, status=TaskStatus.ON_HOLD)
    assert t.status == TaskStatus.ON_HOLD
    work = suggestions.for_field(session, "work_type")
    assert work[0] == "Analiza" and "Moj tip" in work  # ugrađeni pa upisani
    assert "Onboarding partnera" in suggestions.for_field(session, "project_type")
    f = tasks_svc.TaskFilter(owner="Pravna služba")
    assert [x.title for x in tasks_svc.filtered(session, project.id, f)] == ["Čeka partnera"]


def test_migration_keeps_existing_data(tmp_path):
    """Baza iz verzije 0002 (sa zadacima) prelazi na novu šemu bez gubitka podataka."""
    from app.config import get_paths

    paths = get_paths(tmp_path).ensure()
    db = Database(paths)
    command.upgrade(alembic_config(paths.db_url), "0002")
    db.dispose()
    con = sqlite3.connect(paths.db_path)
    pid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    con.execute(
        "insert into projects(id,name,description,client,color,status,archived,sort_order,"
        "created_at,updated_at) values(?,'Stari','','','#000','active',0,0,'2026-01-01',"
        "'2026-01-01')",
        (pid,),
    )
    con.execute(
        "insert into tasks(id,project_id,title,description,status,priority,progress,"
        "planned_cost_minor,sort_order,created_at,updated_at) values(?,?,'Zadatak','',"
        "'review','medium',0,0,0,'2026-01-01','2026-01-01')",
        (tid, pid),
    )
    con.commit()
    con.close()
    db = Database(paths)
    db.upgrade()
    with db.session() as s:
        task = tasks_svc.get(s, tid)
        assert task.status == TaskStatus.REVIEW and task.owner == ""
        tasks_svc.update(s, task, status=TaskStatus.BLOCKED)
        s.commit()
    db.dispose()
