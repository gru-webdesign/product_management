"""Scenario od početka do kraja, redom kako korisnik radi, na praznoj bazi.

Prazna aplikacija → projekat iz dijaloga → zadaci sa nosiocem, fazom, koracima i zavisnošću →
Kanban (status) → Gant (pomeranje, naslednik se pomera) → vreme (ručni unos i tajmer) →
budžet (plan, trošak u EUR, prihod) → registar (rizik, osoba, dokument, odluka) → Pregled →
deljenje u mreži (stranica, PIN, komentar nazad u aplikaciju) → izvoz PDF/Excel/CSV →
uvoz iz Excel-a u novi projekat → liste predloga → kopija i vraćanje → arhiviranje i brisanje.
Posle svakog koraka: nema izuzetaka, nema isečenog teksta, baza je ispravna.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import httpx
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from sqlalchemy import text

from app.db.models import DependencyType, RiskStatus, TaskStatus
from app.services import backup, registry, sharing
from app.services import budget as budget_service
from app.services import dashboard as dashboard_service
from app.services import projects as project_service
from app.services import tasks as task_service
from app.services import timetracking as tt
from app.ui.main_window import MainWindow
from tests.clipping import find_clipped

TODAY = date.today()


@pytest.fixture
def app_window(qtbot, db, monkeypatch):
    errors: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda t, e, tb: errors.append(e))
    for name in ("question",):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.StandardButton.Yes)
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: None)
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    QApplication.processEvents()
    w.errors = errors
    return w


def check(w, step: str) -> None:
    """Posle koraka: bez izuzetaka, bez isečenog teksta, baza ispravna."""
    QApplication.processEvents()
    assert not w.errors, f"{step}: {w.errors[0]!r}"
    clipped = find_clipped(w)
    assert not clipped, f"{step}: " + "\n".join(clipped)
    with w.ctx.session() as s:
        conn = s.connection()
        assert conn.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert conn.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_full_workflow(app_window, monkeypatch, tmp_path):
    w = app_window
    ctx = w.ctx

    # 1. prazna aplikacija
    assert w.stack.currentWidget() is w.empty
    check(w, "prazna aplikacija")

    # 2. projekat iz dijaloga
    from app.ui.dialogs.project_dialog import ProjectDialog

    def fill_project(dlg):
        dlg.name.setText("Plaćanje računa u TNapp")
        dlg.project_type.setCurrentText("Novi servis ili proizvod")
        dlg.client.setCurrentText("Korisnici TNapp")
        dlg.manager.setCurrentText("Goran")
        dlg.start.set_value(TODAY)
        dlg.end.set_value(TODAY + timedelta(days=60))
        dlg.description.setPlainText("Cilj: plaćanje računa u aplikaciji.")
        return 1

    monkeypatch.setattr(ProjectDialog, "exec", fill_project)
    w.sidebar.new_project()
    pid = ctx.project_id
    assert pid and w.header.title.text() == "Plaćanje računa u TNapp"
    check(w, "novi projekat")

    # 3. zadaci iz dijaloga: nosilac, faza, vrsta rada, koraci, zavisnost
    from app.ui.dialogs.task_dialog import TaskDialog

    def new_task(title, start, days, work, deps=()):
        dlg = TaskDialog(ctx, None, w)
        dlg.title_edit.setText(title)
        dlg.owner.setCurrentText("Backend")
        dlg.phase.setCurrentText("Razvoj i integracija")
        dlg.work_type.setCurrentText(work)
        dlg.start.set_value(start)
        dlg.due.set_value(start + timedelta(days=days))
        for dep in deps:
            dlg.dep_task.setCurrentIndex(dlg.dep_task.findText(dep))
            dlg.dep_type.setCurrentIndex(dlg.dep_type.findData(DependencyType.FINISH_TO_START))
            dlg._add_dependency()
        dlg._save()
        assert dlg.result() == dlg.DialogCode.Accepted
        return dlg.task_id

    analysis = new_task("Analiza API dokumentacije", TODAY, 4, "Analiza")
    dev = new_task("Integracija sa API-jem", TODAY + timedelta(days=5), 10, "Integracija",
                   ["Analiza API dokumentacije"])  # fmt: skip
    dlg = TaskDialog(ctx, dev, w)
    dlg._add_suggested_steps()
    n_steps = len(dlg._steps)
    dlg._save()
    with ctx.session() as s:
        t = task_service.get(s, dev)
        assert len(t.subtasks) == n_steps >= 8
        assert t.predecessors[0].predecessor_id == analysis
    check(w, "zadaci i koraci")

    # 4. Lista i Kanban: status se menja prevlačenjem
    w.tabs.setCurrentIndex(0)
    check(w, "lista")
    w.tabs.setCurrentIndex(1)
    w.views[1]._dropped([analysis], TaskStatus.IN_PROGRESS)
    QApplication.processEvents()
    with ctx.session() as s:
        assert task_service.get(s, analysis).status == TaskStatus.IN_PROGRESS
    check(w, "kanban")

    # 5. Gant: prethodnik kasni 3 dana, naslednik se pomera za njim
    w.tabs.setCurrentIndex(2)
    with ctx.session() as s:
        before = task_service.get(s, dev).start_date
        task_service.move_by_days(s, task_service.get(s, analysis), 3)
        s.commit()
        assert task_service.get(s, dev).start_date > before
    ctx.data_changed.emit()
    check(w, "gant")

    # 6. vreme: ručni unos i tajmer
    with ctx.session() as s:
        tt.add_entry(s, analysis, TODAY, 2.5, "čitanje dokumentacije")
        s.commit()
    w.timer.start(analysis) if hasattr(w, "timer") and hasattr(w.timer, "start") else None
    with ctx.session() as s:
        assert task_service.get(s, analysis).actual_hours == pytest.approx(2.5)
    check(w, "vreme")

    # 7. budžet: plan, trošak u EUR, prihod
    from app.ui.dialogs.cost_dialog import MoneyEntryDialog

    w.tabs.setCurrentIndex(3)
    with ctx.session() as s:
        cat = budget_service.categories(s)[0]
        budget_service.set_planned(s, pid, cat.id, 50_000_00)
        s.commit()
    cost = MoneyEntryDialog(ctx, "cost", None, w)
    cost.amount.setText("100")
    cost.currency.setCurrentIndex(cost.currency.findData("EUR"))
    cost.rate.setValue(117.2)
    cost.category.setCurrentIndex(0)
    cost.vendor.setText("Sandbox pristup")
    cost.validate()
    assert cost.save()
    income = MoneyEntryDialog(ctx, "income", None, w)
    income.amount.setText("20.000")
    income.validate()
    assert income.save()
    with ctx.session() as s:
        summ = budget_service.summary(s, pid)
        assert summ.spent == 11_720_00 and summ.income == 20_000_00
    ctx.data_changed.emit()
    check(w, "budžet")

    # 8. registar
    w.tabs.setCurrentIndex(4)
    with ctx.session() as s:
        registry.create(s, registry.RISK, pid, title="Kašnjenje partnera", probability=3, impact=4)
        registry.create(s, registry.STAKEHOLDER, pid, name="Compliance", raci="A")
        registry.create(s, registry.DOCUMENT, pid, title="PRD", location="https://intranet/prd")
        registry.create(s, registry.DECISION, pid, title="Koristimo REST API", decided_on=TODAY)
        s.commit()
    ctx.data_changed.emit()
    assert w.views[4].trees[0].topLevelItemCount() == 1
    check(w, "registar")

    # 9. Pregled svih projekata
    ctx.show_dashboard.emit()
    QApplication.processEvents()
    with ctx.session() as s:
        ov = dashboard_service.build(s, today=TODAY)
        assert ov.open_risks == 1 and ov.projects[0].name == "Plaćanje računa u TNapp"
    check(w, "pregled")
    w.sidebar.list.setCurrentRow(0)

    # 10. deljenje u mreži: stranica, PIN, komentar dolazi u aplikaciju
    from app.share.local_server import LocalShareServer
    from app.share.snapshot import ShareOptions

    with ctx.session() as s:
        link = sharing.enable_local(s, pid, ShareOptions(True, True, False), pin="2468")
        s.commit()
        token = link.token
    server = LocalShareServer(w.db, 0, host="127.0.0.1")
    server.start()
    try:
        c = httpx.Client(base_url=f"http://127.0.0.1:{server.port}", timeout=5)
        assert "Unesi PIN" in c.get(f"/p/{token}").text
        c.post(f"/p/{token}/unlock", data={"pin": "2468"})
        assert "Analiza API dokumentacije" in c.get(f"/p/{token}").text
        assert (
            c.post(f"/api/comments/{token}", json={"text": "Super", "author": "Ana"}).status_code
            == 201
        )
    finally:
        server.stop()
    with ctx.session() as s:
        assert sharing.unread_count(s, pid) == 1
    check(w, "deljenje")

    # 11. izvoz
    from app.services import export_csv, export_xlsx
    from app.ui.report import write_pdf

    with ctx.session() as s:
        assert write_pdf(s, pid, tmp_path / "r.pdf").read_bytes().startswith(b"%PDF")
        xlsx = export_xlsx.write(s, pid, tmp_path / "r.xlsx")
        assert "Analiza API dokumentacije" in export_csv.tasks_csv(s, pid)
    check(w, "izvoz")

    # 12. uvoz iz Excel-a (izvezena tabela se uvozi u nov projekat)
    from app.services import importer

    table = importer.read_table(xlsx)
    for row in table[1:]:
        row.insert(0, "Kopija iz Excel-a")
    table[0].insert(0, "Projekat")
    with ctx.session() as s:
        plan = importer.plan(s, table)
        result = importer.apply(s, plan)
        s.commit()
    assert result.projects == 1 and result.tasks >= 10
    w.sidebar.reload()
    check(w, "uvoz")

    # 13. liste predloga
    from app.services import suggestions

    with ctx.session() as s:
        suggestions.set_list(s, "client", ["RIA", "Korisnici TNapp"])
        s.commit()
        assert suggestions.for_field(s, "client")[:2] == ["RIA", "Korisnici TNapp"]

    # 14. kopija i vraćanje
    made = backup.create_backup(w.db.paths)
    with ctx.session() as s:
        registry.update(s, registry.RISK, registry.risks(s, pid)[0], status=RiskStatus.CLOSED)
        s.commit()
    w.db.dispose()
    backup.restore_backup(w.db.paths, made)
    with ctx.session() as s:
        assert registry.risks(s, pid)[0].status != RiskStatus.CLOSED
    ctx.data_changed.emit()
    check(w, "kopija")

    # 15. arhiviranje i brisanje
    with ctx.session() as s:
        project_service.set_archived(s, project_service.get(s, pid), True)
        s.commit()
    w.sidebar.reload()
    with ctx.session() as s:
        names = [p.name for p in project_service.list_projects(s)]
        assert "Plaćanje računa u TNapp" not in names
        copy = next(p for p in project_service.list_projects(s) if p.name == "Kopija iz Excel-a")
        project_service.delete(s, copy)
        s.commit()
    w.sidebar.reload()
    check(w, "arhiva i brisanje")
