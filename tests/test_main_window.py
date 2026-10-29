from __future__ import annotations

from app import APP_NAME
from app.ui.main_window import MainWindow


def test_main_window_opens(qtbot, db):
    window = MainWindow(db)
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == APP_NAME
    assert str(db.paths.db_path) in window.statusBar().currentMessage()
