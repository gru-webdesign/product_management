"""Izvoz u CSV za Excel (UTF-8 sa BOM-om i tačka-zarez kao separator, kao u srpskom Excel-u)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from sqlalchemy.orm import Session

from app.labels import PRIORITY, TASK_STATUS
from app.services import budget as budget_service
from app.services import tasks as task_service
from app.services.money import from_minor

DELIMITER = ";"


def _d(value) -> str:
    return value.strftime("%d.%m.%Y.") if value else ""


def _n(value) -> str:
    """Broj sa decimalnim zarezom (Excel sa srpskim podešavanjima ga čita kao broj)."""
    if value is None or value == "":
        return ""
    return f"{value}".replace(".", ",")


def tasks_csv(session: Session, project_id: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=DELIMITER, lineterminator="\r\n")
    w.writerow(
        [
            "Nivo",
            "Naziv",
            "Status",
            "Prioritet",
            "Početak",
            "Rok",
            "Progres %",
            "Procena h",
            "Utrošeno h",
            "Planirani trošak",
            "Tagovi",
            "Opis",
        ]
    )
    for t, depth in task_service.tree(session, project_id):
        w.writerow(
            [
                depth,
                ("  " * depth) + t.title,
                TASK_STATUS[t.status],
                PRIORITY[t.priority],
                _d(t.start_date),
                _d(t.due_date),
                t.progress,
                _n(t.estimate_hours),
                _n(t.actual_hours),
                _n(from_minor(t.planned_cost_minor)) if t.planned_cost_minor else "",
                ", ".join(sorted(g.name for g in t.tags)),
                t.description.replace("\r", " ").replace("\n", " "),
            ]
        )
    return buf.getvalue()


def costs_csv(session: Session, project_id: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=DELIMITER, lineterminator="\r\n")
    base = budget_service.base_currency(session)
    w.writerow(
        [
            "Datum",
            "Vrsta",
            "Kategorija",
            "Zadatak",
            "Dobavljač / opis",
            "Iznos",
            "Valuta",
            "Kurs",
            f"Iznos ({base})",
            "Napomena",
        ]
    )
    for c in budget_service.costs(session, project_id):
        w.writerow(
            [
                _d(c.date),
                "Trošak",
                c.category.name,
                c.task.title if c.task else "",
                c.vendor,
                _n(from_minor(c.amount_minor)),
                c.currency,
                _n(c.exchange_rate),
                _n(from_minor(c.amount_base_minor)),
                c.note.replace("\n", " "),
            ]
        )
    for i in budget_service.incomes(session, project_id):
        w.writerow(
            [
                _d(i.date),
                "Prihod",
                "",
                "",
                i.description,
                _n(from_minor(i.amount_minor)),
                i.currency,
                _n(i.exchange_rate),
                _n(from_minor(i.amount_base_minor)),
                "",
            ]
        )
    return buf.getvalue()


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8-sig", newline="")
