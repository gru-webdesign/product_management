"""Tab Registar i nova polja u dijalozima (UI, bez prozora)."""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.db.models import RiskStatus, TaskStatus
from app.services import registry
from app.ui.dialogs.registry_dialogs import RiskDialog
from app.ui.main_window import MainWindow
from app.ui.views.registry_view import RegistryView
from scripts.seed_demo import seed


@pytest.fixture
def window(qtbot, db, monkeypatch):
    with db.session() as s:
        seed(s, today=date.today())
        s.commit()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.show()
    return w


def registry_view(w) -> RegistryView:
    w.tabs.setCurrentIndex(4)
    view = w.views[4]
    assert isinstance(view, RegistryView)
    return view


def test_registry_shows_demo_items(window):
    view = registry_view(window)
    # otvoreni rizici (zatvoreni su skriveni), ljudi, dokumenta, odluke
    assert view.trees[0].topLevelItemCount() == 4
    assert view.section_buttons[0].text().endswith("4")
    assert view.trees[1].topLevelItemCount() == 7
    assert view.trees[2].topLevelItemCount() == 5
    assert view.trees[3].topLevelItemCount() == 2
    first = view.trees[0].topLevelItem(0)
    assert first.text(2).startswith("Visok")  # najveća ocena prva
    view.show_closed.setChecked(True)
    assert view.trees[0].topLevelItemCount() == 5


def test_add_edit_status_delete_risk(window, monkeypatch):
    view = registry_view(window)

    def fill(dlg):
        dlg.title_field.setText("Novi rizik")
        dlg.probability.setCurrentIndex(3)
        dlg.impact.setCurrentIndex(3)
        assert "Kritičan" in dlg.score.text()
        dlg.owner.setCurrentText("Moj tim")
        return 1

    monkeypatch.setattr(RiskDialog, "exec", fill)
    new_id = view.add("risk")
    assert new_id
    titles = [
        view.trees[0].topLevelItem(i).text(0) for i in range(view.trees[0].topLevelItemCount())
    ]
    assert titles[0] == "Novi rizik"

    monkeypatch.setattr(RiskDialog, "exec", lambda dlg: (dlg.title_field.setText("Izmenjen"), 1)[1])
    view.edit(0, new_id)
    view._set_status(0, [new_id], RiskStatus.CLOSED)
    with window.ctx.session() as s:
        risk = registry.get(s, registry.RISK, new_id)
        assert (risk.title, risk.owner, risk.status) == ("Izmenjen", "Moj tim", RiskStatus.CLOSED)
    view.delete(0, [new_id])
    with window.ctx.session() as s, pytest.raises(ValueError):
        registry.get(s, registry.RISK, new_id)


def test_task_dialog_new_fields_and_blocked_status(window):
    from app.ui.dialogs.task_dialog import TaskDialog

    with window.ctx.session() as s:
        from app.services import tasks as task_service

        task = next(
            t
            for t, _ in task_service.tree(s, window.ctx.project_id)
            if t.title == "Provera sankcionih lista"
        )
        tid = task.id
    dlg = TaskDialog(window.ctx, tid, window)
    assert dlg.owner.value() == "AML" and dlg.phase.value() == "Discovery i analiza"
    assert dlg.status.currentData() == TaskStatus.BLOCKED
    dlg.owner.setCurrentText("Spoljni konsultant")
    dlg.phase.setCurrentText("Ugovaranje")
    values = dlg.values()
    assert values["owner"] == "Spoljni konsultant" and values["phase"] == "Ugovaranje"
    dlg.close()


def test_task_steps_tab_and_parent_grouping(window):
    from app.ui.dialogs.task_dialog import TaskDialog

    with window.ctx.session() as s:
        from app.services import tasks as task_service

        dev = next(
            t
            for t, _ in task_service.tree(s, window.ctx.project_id)
            if t.title == "Razvoj integracije"
        )
        dev_id = dev.id
    dlg = TaskDialog(window.ctx, dev_id, window)
    # postojeći koraci + predlozi za vrstu rada Integracija (bez onih koji već postoje)
    assert [s["title"] for s in dlg._steps][0] == "Analiza API dokumentacije"
    assert "Analiza API dokumentacije" not in dlg._step_suggestions()
    assert "Mapiranje polja, statusa i kodova grešaka" in dlg._step_suggestions()
    assert dlg.tabs.tabText(1) == "Koraci 0/4"
    dlg.step_input.setCurrentText("Dogovor o formatu callback-a")
    dlg._add_step()
    dlg.steps_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert dlg.tabs.tabText(1) == "Koraci 1/5"
    # „Deo zadatka“: zadaci iz iste faze su prvi
    dlg.phase.setCurrentText("Discovery i analiza")
    labels = [dlg.parent_combo.itemText(i) for i in range(dlg.parent_combo.count())]
    assert labels[0].startswith("Samostalan") and labels[2] == "Faza Discovery i analiza"
    assert labels[3] == "KYB dokumentacija partnera" and "Ostale faze" in labels
    dlg.phase.setCurrentText("Razvoj i integracija")
    dlg._save()
    with window.ctx.session() as s:
        steps = {c.title: c.status for c in task_service.get(s, dev_id).subtasks}
    assert steps["Analiza API dokumentacije"] == TaskStatus.DONE
    assert "Dogovor o formatu callback-a" in steps


def test_new_task_with_suggested_steps(window):
    from app.ui.dialogs.task_dialog import TaskDialog

    dlg = TaskDialog(window.ctx, None, window)
    dlg.title_edit.setText("Uvođenje plaćanja QR kodom")
    dlg.work_type.setCurrentText("Razvoj")
    dlg._add_suggested_steps()
    n = len(dlg._steps)
    assert n >= 8
    dlg._save()
    with window.ctx.session() as s:
        from app.services import tasks as task_service

        task = task_service.get(s, dlg.task_id)
        assert len(task.subtasks) == n and task.subtasks[0].work_type == "Razvoj"
