"""Nijedan tekst ne sme da bude isečen: prozor na 1024×680 i 1280×800, svi prikazi i dijalozi.

Detektor (tests/clipping.py) poredi stvarnu veličinu svake labele, dugmeta i polja sa veličinom
koju traži njihov tekst. Ovo hvata greške koje se vide na Windows-u (uvećan font, mali ekran).
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

from app.ui.main_window import MainWindow
from scripts.seed_demo import seed, seed_extra
from tests.clipping import find_clipped


@pytest.fixture
def capture(monkeypatch):
    found: list[str] = []

    def fake_exec(self):
        self.show()
        QApplication.processEvents()
        found.extend(find_clipped(self))
        tabs = getattr(self, "tabs", None)
        if tabs is not None:
            for i in range(tabs.count()):
                tabs.setCurrentIndex(i)
                QApplication.processEvents()
                found.extend(find_clipped(self))
        self.close()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    for name in ("question", "warning", "information", "critical", "about"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: QMessageBox.StandardButton.No)
    for name in ("getText", "getMultiLineText", "getItem"):
        monkeypatch.setattr(QInputDialog, name, lambda *a, **k: ("", False))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    from PySide6.QtGui import QDesktopServices

    monkeypatch.setattr(QDesktopServices, "openUrl", lambda *a, **k: True)
    return found


def _window(qtbot, db, size):
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.resize(*size)
    w.show()
    QApplication.processEvents()
    return w


@pytest.mark.parametrize("size", [(1024, 680), (1280, 800)])
def test_empty_app_and_new_project_dialog(qtbot, db, capture, size):
    w = _window(qtbot, db, size)
    capture.extend(find_clipped(w))
    w.sidebar.new_project()
    w.import_tasks()
    assert not capture, "\n".join(capture)


@pytest.mark.parametrize("size", [(1024, 680), (1280, 800)])
def test_all_views_and_dialogs_with_data(qtbot, db, capture, size):
    with db.session() as s:
        seed_extra(s, today=date.today())
        seed(s, today=date.today())
        s.commit()
    w = _window(qtbot, db, size)
    for row in range(w.sidebar.list.count()):
        w.sidebar.list.setCurrentRow(row)
        for i in range(w.tabs.count()):
            w.tabs.setCurrentIndex(i)
            QApplication.processEvents()
            QApplication.processEvents()
            capture.extend(find_clipped(w))
    from app.services import tasks as task_service
    from app.ui.dialogs.task_dialog import TaskDialog

    with db.session() as s:
        tid = next(t.id for t, _ in task_service.tree(s, w.ctx.project_id) if t.subtasks)
    TaskDialog(w.ctx, tid, w).exec()
    TaskDialog(w.ctx, None, w).exec()
    w.tabs.setCurrentIndex(4)
    for kind in ("risk", "stakeholder", "document", "decision"):
        w.views[4].add(kind)
    w.tabs.setCurrentIndex(3)
    for kind in ("cost", "income"):
        w.views[3]._edit(kind)
    w.views[3]._edit_budget()
    w.open_settings()
    assert not sorted(set(capture)), "\n".join(sorted(set(capture)))
