"""Srpski nazivi i boje za enum vrednosti (koriste ih UI i stranica za deljenje)."""

from __future__ import annotations

from app.db.models import DependencyType, Priority, ProjectStatus, TaskStatus

TASK_STATUS = {
    TaskStatus.TODO: "Za uraditi",
    TaskStatus.IN_PROGRESS: "U toku",
    TaskStatus.REVIEW: "Na proveri",
    TaskStatus.DONE: "Završeno",
}

TASK_STATUS_COLOR = {
    TaskStatus.TODO: "#8B8D98",
    TaskStatus.IN_PROGRESS: "#3E63DD",
    TaskStatus.REVIEW: "#F76B15",
    TaskStatus.DONE: "#30A46C",
}

PRIORITY = {
    Priority.LOW: "Nizak",
    Priority.MEDIUM: "Srednji",
    Priority.HIGH: "Visok",
    Priority.URGENT: "Hitno",
}

PRIORITY_COLOR = {
    Priority.LOW: "#8B8D98",
    Priority.MEDIUM: "#3E63DD",
    Priority.HIGH: "#F76B15",
    Priority.URGENT: "#E5484D",
}

PROJECT_STATUS = {
    ProjectStatus.PLANNED: "Planiran",
    ProjectStatus.ACTIVE: "Aktivan",
    ProjectStatus.ON_HOLD: "Na čekanju",
    ProjectStatus.DONE: "Završen",
}

DEPENDENCY_TYPE = {
    DependencyType.FINISH_TO_START: "Završi → počni",
    DependencyType.START_TO_START: "Počni → počni",
    DependencyType.FINISH_TO_FINISH: "Završi → završi",
}

FIELD = {
    "name": "naziv",
    "title": "naziv",
    "description": "opis",
    "client": "klijent",
    "color": "boja",
    "start_date": "početak",
    "end_date": "kraj",
    "due_date": "rok",
    "status": "status",
    "priority": "prioritet",
    "progress": "progres",
    "estimate_hours": "procena sati",
    "actual_hours": "utrošeni sati",
    "planned_cost_minor": "planirani trošak",
    "archived": "arhiviran",
    "parent_id": "nadređeni zadatak",
    "tags": "tagovi",
}

PROJECT_COLORS = [
    "#5B5BD6",
    "#3E63DD",
    "#0090FF",
    "#12A594",
    "#30A46C",
    "#F76B15",
    "#E5484D",
    "#D6409F",
    "#8E4EC6",
    "#8B8D98",
]


def display_value(field: str, value) -> str:
    """Čitljiv prikaz vrednosti u istoriji izmena."""
    if value is None or value == "":
        return "—"
    if isinstance(value, TaskStatus):
        return TASK_STATUS[value]
    if isinstance(value, Priority):
        return PRIORITY[value]
    if isinstance(value, ProjectStatus):
        return PROJECT_STATUS[value]
    if isinstance(value, bool):
        return "da" if value else "ne"
    if field == "planned_cost_minor":
        from app.services.money import format_money

        return format_money(int(value))
    if field == "progress":
        return f"{value}%"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y.")
    return str(value)
