from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app import APP_NAME
from app.services import projects as project_service
from app.ui import theme
from app.ui.main_window import MainWindow


def make_window(qtbot, db) -> MainWindow:
    window = MainWindow(db)
    qtbot.addWidget(window)
    window.show()
    return window


def test_main_window_opens_with_empty_state(qtbot, db):
    window = make_window(qtbot, db)
    assert window.windowTitle() == APP_NAME
    assert window.stack.currentIndex() == 0  # nema projekata → prazan ekran
    assert window.statusBar().currentMessage() == ""  # putanja baze je u „O programu"


def test_project_appears_and_is_selected(qtbot, db):
    window = make_window(qtbot, db)
    window.ctx.run(lambda s: project_service.create(s, name="Prvi", client="Firma"))
    assert window.sidebar.list.count() == 1
    assert window.stack.currentIndex() == 1
    assert window.header.title.text() == "Prvi"
    assert "Firma" in window.header.meta_text()


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


def test_dashboard_navigation(qtbot, db):
    from datetime import date

    from scripts.seed_demo import seed

    with db.session() as s:
        seed(s, today=date.today())
        s.commit()
    window = make_window(qtbot, db)
    window.ctx.show_dashboard.emit()
    assert window.stack.currentWidget() is window.dashboard
    assert window.sidebar.dashboard_button.isChecked()
    assert window.dashboard.projects.topLevelItemCount() == 1
    assert window.dashboard.s_open.value.text() == "6"
    item = window.dashboard.projects.topLevelItem(0)
    window.dashboard._open_project(item)
    qtbot.wait(20)
    assert window.stack.currentIndex() == 1
    assert not window.sidebar.dashboard_button.isChecked()
    assert window.sidebar.list.currentRow() == 0


def test_new_project_from_template_and_save_as_template(qtbot, db, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from app.services import tasks as task_service
    from app.services import templates as template_service
    from app.ui.dialogs.project_dialog import ProjectDialog

    def fake_exec(dlg):
        dlg.name.setText("Sajt za pekaru")
        dlg.template.setCurrentIndex(dlg.template.findData("builtin:sajt"))
        assert dlg.start.value() is not None  # šablon sam postavlja početak
        return 1

    monkeypatch.setattr(ProjectDialog, "exec", fake_exec)
    window = make_window(qtbot, db)
    window.sidebar.new_project()
    assert window.header.title.text() == "Sajt za pekaru"
    with db.session() as s:
        assert len(task_service.tree(s, window.ctx.project_id)) == 10

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Pekara šablon", True))
    window.save_template()
    with db.session() as s:
        names = [i.name for i in template_service.list_templates(s)]
    assert "Pekara šablon" in names


def test_reminders_check_once_and_toggle(qtbot, db):
    from datetime import date

    from app.services import projects as ps
    from app.services import tasks as ts
    from app.services.defaults import set_setting

    window = make_window(qtbot, db)
    pid = window.ctx.run(lambda s: ps.create(s, name="Rok").id)
    window.ctx.run(lambda s: ts.create(s, pid, title="Predaja", due_date=date.today()))
    first = window.reminders.check()
    assert [r.title for r in first] == ["Predaja"]
    assert "rok danas: 1" in window.statusBar().currentMessage()
    assert window.reminders.check() == []  # isti dan ne ponavlja
    assert len(window.reminders.check(force=True)) == 1
    window.ctx.run(lambda s: set_setting(s, "reminders_enabled", "0"))
    window.ctx.run(lambda s: ts.create(s, pid, title="Još jedan", due_date=date.today()))
    assert window.reminders.check() == []  # isključeno u podešavanjima
