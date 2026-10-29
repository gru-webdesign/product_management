from __future__ import annotations

from datetime import date, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from app.db.models import Priority, TaskStatus
from app.services import tasks as task_service
from app.ui import theme
from app.ui.dialogs.task_dialog import TaskDialog
from app.ui.main_window import MainWindow
from app.ui.views.list_view import C_TITLE, ROLE_ID, ListView
from scripts.seed_demo import seed


@pytest.fixture
def window(qtbot, db):
    with db.session() as s:
        seed(s, today=date.today())
        s.commit()
    theme.apply(QApplication.instance(), "light")
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.show()
    return w


def list_view(window) -> ListView:
    window.tabs.setCurrentIndex(0)
    view = window.views[0]
    assert isinstance(view, ListView)
    return view


def all_items(tree):
    out, stack = [], [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop(0)
        out.append(it)
        stack[:0] = [it.child(i) for i in range(it.childCount())]
    return out


def test_tree_shows_all_tasks_with_subtasks(window):
    view = list_view(window)
    assert view.tree.topLevelItemCount() == 8
    assert len(all_items(view.tree)) == 10
    design = next(i for i in all_items(view.tree) if i.text(C_TITLE) == "Vizuelni dizajn")
    assert design.childCount() == 2 and design.isExpanded()
    assert view.count_label.text() == "10 zadataka"


def test_filters_switch_to_flat_list(window):
    view = list_view(window)
    view.status_filter.setCurrentIndex(view.status_filter.findData(TaskStatus.DONE))
    titles = [i.text(C_TITLE) for i in all_items(view.tree)]
    assert titles == ["Brief i prikupljanje sadržaja", "Wireframe glavnih stranica"]
    assert view.clear_button.isVisible()
    view.clear_filters()
    assert len(all_items(view.tree)) == 10


def test_search_from_header(window, qtbot):
    view = list_view(window)
    window.ctx.set_search("meni")
    titles = [i.text(C_TITLE) for i in all_items(view.tree)]
    assert titles == ["Vizuelni dizajn  ›  Meni i cenovnik"]
    window.ctx.set_search("")


def test_sort_by_due_and_back(window):
    view = list_view(window)
    view._sort_clicked(4)
    assert view.tree.sortColumn() == 4
    view._sort_clicked(4)
    view._sort_clicked(4)
    assert view._sort_col is None


def test_status_change_from_menu_action(window):
    view = list_view(window)
    item = next(i for i in all_items(view.tree) if i.text(C_TITLE) == "Odobrenje klijenta")
    view.tree.setCurrentItem(item)
    tid = item.data(C_TITLE, ROLE_ID)
    view.set_status(TaskStatus.DONE)
    with window.db.session() as s:
        task = task_service.get(s, tid)
        assert task.status == TaskStatus.DONE and task.progress == 100


def test_new_task_dialog_saves(window, qtbot):
    dlg = TaskDialog(window.ctx, None, window)
    qtbot.addWidget(dlg)
    dlg.title_edit.setText("Napraviti 404 stranicu")
    dlg.priority.setCurrentIndex(dlg.priority.findData(Priority.HIGH))
    dlg.start.set_value(date.today())
    dlg.due.set_value(date.today() + timedelta(days=2))
    dlg.cost.setText("1.500,50")
    dlg.tags.setText("razvoj, Novo")
    dlg._save()
    assert dlg.result() == dlg.DialogCode.Accepted
    with window.db.session() as s:
        task = task_service.get(s, dlg.task_id)
        assert task.priority == Priority.HIGH
        assert task.planned_cost_minor == 150050
        assert sorted(t.name for t in task.tags) == ["novo", "razvoj"]
    assert len(all_items(list_view(window).tree)) == 11


def test_dialog_validation_message(window, qtbot):
    dlg = TaskDialog(window.ctx, None, window)
    qtbot.addWidget(dlg)
    dlg._save()
    assert dlg.error.text() == "Unesi naziv zadatka."
    dlg.title_edit.setText("x")
    dlg.start.set_value(date(2026, 5, 2))
    dlg.due.set_value(date(2026, 5, 1))
    dlg._save()
    assert "pre roka" in dlg.error.text()


def test_edit_dialog_mark_done_and_dependency(window, qtbot):
    with window.db.session() as s:
        review = next(
            t
            for t, _ in task_service.tree(s, window.ctx.project_id)
            if t.title == "Odobrenje klijenta"
        )
        rid = review.id
    dlg = TaskDialog(window.ctx, rid, window)
    qtbot.addWidget(dlg)
    assert dlg.tabs.count() == 5
    assert dlg.deps_list.count() == 1  # čeka na Vizuelni dizajn
    dlg.note_edit.setText("Poslat mejl klijentu")
    dlg._add_note()
    assert dlg.notes_list.count() == 1
    dlg.status.setCurrentIndex(dlg.status.findData(TaskStatus.DONE))
    dlg._save()
    with window.db.session() as s:
        t = task_service.get(s, rid)
        assert t.status == TaskStatus.DONE and t.progress == 100
