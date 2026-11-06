"""Uvoz zadataka iz Excel/CSV tabele."""

from __future__ import annotations

import datetime as dt

import pytest

from app.db.models import Priority, TaskStatus
from app.services import importer
from app.services import projects as projects_svc
from app.services import tasks as tasks_svc

D = dt.date(2026, 11, 6)


def test_template_roundtrip(session, tmp_path):
    path = importer.write_template(tmp_path / "sablon.xlsx")
    table = importer.read_table(path)
    assert table[0][:2] == ["Projekat", "Zadatak"]
    plan = importer.plan(session, table)
    assert plan.new_projects == ["Integracija partnera X"]
    assert not plan.skipped and not plan.unknown_columns and not plan.warnings
    result = importer.apply(session, plan, today=D)
    assert (result.tasks, result.projects, result.dependencies) == (4, 1, 2)
    p = next(x for x in projects_svc.list_projects(session) if x.name == "Integracija partnera X")
    tree = {t.title: (t, depth) for t, depth in tasks_svc.tree(session, p.id)}
    done, _ = tree["Analiza API dokumentacije"]
    assert done.status == TaskStatus.DONE and done.progress == 100 and done.actual_hours == 14
    assert done.start_date == dt.date(2026, 2, 3) and done.owner == "Backend"
    step, depth = tree["Mapiranje kodova grešaka"]
    assert depth == 1 and step.parent.title == "Integracija sa API-jem"
    api, _ = tree["Integracija sa API-jem"]
    assert api.priority == Priority.HIGH and api.planned_cost_minor == 20000000
    assert [t.name for t in api.tags] == ["partner"]


def test_loose_columns_csv_and_default_project(session, tmp_path):
    proj = projects_svc.create(session, name="Moj projekat")
    tasks_svc.create(session, proj.id, title="Postojeći zadatak")
    csv_path = tmp_path / "stari.csv"
    csv_path.write_text(
        "Naziv;Stanje;Odgovoran;Kraj;Napomena;Zavisi od;Nešto drugo\n"
        "Ugovor sa partnerom;done;Pravna služba;15.03.2026.;potpisano;Postojeći zadatak;x\n"
        "Izveštaj NBS;bla;;2026-04-01;;;\n"
        ";U toku;;;;;\n",
        encoding="cp1250",
    )
    table = importer.read_table(csv_path)
    with pytest.raises(ValueError):
        importer.plan(session, [["Nešto", "Drugo"], ["a", "b"]])  # nema kolone sa nazivom
    plan = importer.plan(session, table, default_project="Moj projekat")
    assert plan.unknown_columns == ["Nešto drugo"] and plan.new_projects == []
    assert plan.skipped == ["Red 4: nema naziva zadatka"]
    assert any("nepoznat status" in w for w in plan.warnings)
    result = importer.apply(session, plan, today=D)
    assert result.tasks == 2 and result.dependencies == 1
    ugovor = next(
        t for t, _ in tasks_svc.tree(session, proj.id) if t.title == "Ugovor sa partnerom"
    )
    assert ugovor.due_date == dt.date(2026, 3, 15) and ugovor.description == "potpisano"
    assert ugovor.predecessors[0].predecessor.title == "Postojeći zadatak"


def test_parse_helpers():
    assert importer.parse_date("05.11.2026.") == dt.date(2026, 11, 5)
    assert importer.parse_date(46000) == dt.date(2025, 12, 9)
    assert importer.parse_number("1.500,50 RSD") == importer.Decimal("1500.50")
    with pytest.raises(ValueError):
        importer.parse_date("sutra")


def test_import_dialog(qtbot, db, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    from app.ui.context import AppContext
    from app.ui.dialogs.import_dialog import ImportDialog

    with db.session() as s:
        p = projects_svc.create(s, name="Godišnji zadaci")
        s.commit()
        pid = p.id
    ctx = AppContext(db)
    ctx.project_id = pid
    path = importer.write_template(tmp_path / "t.xlsx")
    dlg = ImportDialog(ctx)
    qtbot.addWidget(dlg)
    assert not dlg.import_button.isEnabled()
    assert dlg.load(path)
    assert dlg.preview.topLevelItemCount() == 4
    assert dlg.import_button.text() == "Uvezi 4 zadataka"
    assert "Integracija partnera X" in dlg.summary.text()
    dlg.do_import()
    assert dlg.result.tasks == 4 and dlg.result.projects == 1
    assert not dlg.load(tmp_path / "nema.pdf")


def test_exports_do_not_turn_text_into_formulas(session, tmp_path):
    from openpyxl import load_workbook

    from app.services import export_csv, export_xlsx

    p = projects_svc.create(session, name="P")
    tasks_svc.create(session, p.id, title='=HYPERLINK("http://x","klik")', owner="+381 11 222")
    path = export_xlsx.write(session, p.id, tmp_path / "x.xlsx")
    wb = load_workbook(path)
    assert not [c for ws in wb for row in ws.iter_rows() for c in row if c.data_type == "f"]
    assert any(str(c.value).startswith("=HYPERLINK") for c in wb["Zadaci"][2])  # tekst je sačuvan
    text = export_csv.tasks_csv(session, p.id)
    assert "'=HYPERLINK" in text and "'+381" in text
    assert export_csv.safe_cell("-12,50") == "-12,50"  # broj ostaje broj


def test_importer_survives_garbage(session):
    import random

    rng = random.Random(7)
    header = [h for h, _ in importer.TEMPLATE_HELP]
    junk = [None, "", " ", "x" * 500, -5, 0, 1e12, 3.7, "31.02.2026", "2026-13-01"]
    junk += ["abc", dt.datetime(2026, 1, 1), "=1+1", "Završeno", "1.000,5", "50%", "Ž;č,ć", "\t"]
    for _ in range(30):
        table = [header] + [[rng.choice(junk) for _ in header] for _ in range(rng.randint(0, 40))]
        try:
            plan = importer.plan(session, table, default_project="Smeće")
        except ValueError:
            continue
        importer.apply(session, plan, today=D)
        session.flush()
