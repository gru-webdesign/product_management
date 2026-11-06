"""Dimni test: svaka akcija iz menija i svaki dijalog se otvara bez izuzetka, u obe teme.

Modalni dijalozi se ne čekaju: exec() samo prikaže prozor, obradi događaje i vrati Otkaži.
Izuzetak bačen u Qt slotu (koji bi u aplikaciji samo ispisao grešku) obara test.
"""

from __future__ import annotations

import sys
from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

from app.ui import theme
from app.ui.main_window import MainWindow
from scripts.seed_demo import seed, seed_extra

SKIP = {"Izlaz"}  # zatvara prozor


@pytest.fixture
def window(qtbot, db, monkeypatch, tmp_path):
    with db.session() as s:
        seed_extra(s, today=date.today())
        seed(s, today=date.today())
        s.commit()
    opened: list[str] = []

    def fake_exec(self):
        opened.append(type(self).__name__)
        self.show()
        QApplication.processEvents()
        self.close()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "about", lambda *a, **k: opened.append("About"))
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.StandardButton.No)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(QDesktopServices, "openUrl", lambda *a, **k: True)
    from app.services import updates

    monkeypatch.setattr(updates, "check", lambda *a, **k: None)
    errors: list[BaseException] = []
    monkeypatch.setattr(sys, "excepthook", lambda t, e, tb: errors.append(e))
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.resize(1300, 850)
    w.show()
    w.opened, w.errors = opened, errors
    return w


def all_actions(w):
    for menu_action in w.menuBar().actions():
        menu = menu_action.menu()
        stack = [menu]
        while stack:
            m = stack.pop()
            for a in m.actions():
                if a.menu():
                    stack.append(a.menu())
                elif not a.isSeparator() and a.text():
                    yield a


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_every_menu_action_and_tab(window, mode):
    theme.apply(QApplication.instance(), mode)
    w = window
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        QApplication.processEvents()
    triggered = []
    for action in list(all_actions(w)):
        text = action.text().replace("&", "")
        if text in SKIP or not action.isEnabled():
            continue
        action.trigger()
        QApplication.processEvents()
        triggered.append(text)
        assert not w.errors, f"{text}: {w.errors[0]!r}"
    assert len(triggered) > 20
    assert {"SettingsDialog", "ImportDialog", "RestoreDialog"} <= set(w.opened)
    theme.apply(QApplication.instance(), "dark")


def test_every_project_every_view(window):
    w = window
    for pid in [w.sidebar.list.item(i).data(0x0100) for i in range(w.sidebar.list.count())]:
        if not pid:
            continue
        w.ctx.select_project(pid)
        for i in range(w.tabs.count()):
            w.tabs.setCurrentIndex(i)
            w.repaint()
        assert not w.errors, repr(w.errors[:1])


def test_open_every_task_and_registry_dialog(window):
    from app.services import registry
    from app.services import tasks as task_service
    from app.ui.dialogs.registry_dialogs import (
        DecisionDialog,
        DocumentDialog,
        RiskDialog,
        StakeholderDialog,
    )
    from app.ui.dialogs.task_dialog import TaskDialog

    w = window
    pid = w.ctx.project_id
    with w.ctx.session() as s:
        ids = [t.id for t, _ in task_service.tree(s, pid)]
    for tid in ids:
        dlg = TaskDialog(w.ctx, tid, w)
        for i in range(dlg.tabs.count()):
            dlg.tabs.setCurrentIndex(i)
            dlg.repaint()
        dlg._save()  # čuvanje bez izmena ne sme ništa da pokvari
        dlg.close()
    w.tabs.setCurrentIndex(4)
    view = w.views[4]
    view.reload()
    for section, (_kind, _cls) in enumerate(
        [
            (registry.RISK, RiskDialog),
            (registry.STAKEHOLDER, StakeholderDialog),
            (registry.DOCUMENT, DocumentDialog),
            (registry.DECISION, DecisionDialog),
        ]
    ):
        tree = view.trees[section]
        for i in range(tree.topLevelItemCount()):
            view.edit(section, tree.topLevelItem(i).data(0, 0x0100))
    assert {"RiskDialog", "StakeholderDialog", "DocumentDialog", "DecisionDialog"} <= set(w.opened)
    assert not w.errors, repr(w.errors[:1])
