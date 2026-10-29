from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app import APP_NAME
from app.services import projects as project_service
from app.ui import theme
from app.ui.main_window import MainWindow


def make_window(qtbot, db) -> MainWindow:
    theme.apply(QApplication.instance(), "light")
    window = MainWindow(db)
    qtbot.addWidget(window)
    window.show()
    return window


def test_main_window_opens_with_empty_state(qtbot, db):
    window = make_window(qtbot, db)
    assert window.windowTitle() == APP_NAME
    assert window.stack.currentIndex() == 0  # nema projekata → prazan ekran
    assert str(db.paths.db_path) in window.statusBar().currentMessage()


def test_project_appears_and_is_selected(qtbot, db):
    window = make_window(qtbot, db)
    window.ctx.run(lambda s: project_service.create(s, name="Prvi", client="Firma"))
    assert window.sidebar.list.count() == 1
    assert window.stack.currentIndex() == 1
    assert window.header.title.text() == "Prvi"
    assert "Firma" in window.header.meta.text()


def test_archive_hides_project(qtbot, db):
    window = make_window(qtbot, db)
    window.ctx.run(lambda s: project_service.create(s, name="A"))
    window.ctx.run(lambda s: project_service.create(s, name="B"))
    window.sidebar.list.setCurrentRow(0)
    window.sidebar.toggle_archive_current()
    assert window.sidebar.list.count() == 1
    window.sidebar.show_archived.setChecked(True)
    assert window.sidebar.list.count() == 2


def test_tabs_and_dark_theme(qtbot, db):
    window = make_window(qtbot, db)
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Lista",
        "Kanban",
        "Gant",
        "Budžet",
    ]
    theme.apply(QApplication.instance(), "dark")
    assert theme.tokens().name == "dark"
    theme.apply(QApplication.instance(), "light")
