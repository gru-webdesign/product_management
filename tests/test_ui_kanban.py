from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from app.db.models import TaskStatus
from app.services import tasks as task_service
from app.ui import theme
from app.ui.main_window import MainWindow
from app.ui.views.kanban_view import ROLE_ID, KanbanView
from scripts.seed_demo import seed


@pytest.fixture
def kanban(qtbot, db):
    with db.session() as s:
        seed(s, today=date.today())
        s.commit()
    theme.apply(QApplication.instance(), "light")
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.show()
    w.tabs.setCurrentIndex(1)
    view = w.views[1]
    assert isinstance(view, KanbanView)
    return w, view


def counts(view):
    return {st: f.list.count() for st, f in view.columns.items()}


def test_columns_filled(kanban):
    _, view = kanban
    assert counts(view) == {
        TaskStatus.TODO: 6,
        TaskStatus.IN_PROGRESS: 2,
        TaskStatus.REVIEW: 0,
        TaskStatus.DONE: 2,
    }
    assert view.columns[TaskStatus.TODO].count.text() == "6"


def test_hide_subtasks(kanban):
    _, view = kanban
    view.show_subtasks.setChecked(False)
    assert counts(view)[TaskStatus.IN_PROGRESS] == 1


def test_drop_changes_status(kanban):
    w, view = kanban
    item = view.columns[TaskStatus.TODO].list.item(0)
    tid = item.data(ROLE_ID)
    view._dropped([tid], TaskStatus.REVIEW)
    assert counts(view)[TaskStatus.REVIEW] == 1
    with w.db.session() as s:
        assert task_service.get(s, tid).status == TaskStatus.REVIEW


def test_quick_add(kanban):
    w, view = kanban
    frame = view.columns[TaskStatus.DONE]
    frame.quick.setText("Već urađeno")
    view._quick_add(frame)
    assert counts(view)[TaskStatus.DONE] == 3
    assert frame.quick.text() == ""


def test_search_filters_cards(kanban):
    w, view = kanban
    w.ctx.set_search("objava")
    assert sum(counts(view).values()) == 1
    w.ctx.set_search("")
