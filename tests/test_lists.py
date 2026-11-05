"""Liste predloga: uređivanje u Podešavanjima i šta se nudi u padajućim listama."""

from __future__ import annotations

from app.services import projects as projects_svc
from app.services import suggestions


def test_client_list_edit_hide_and_reset(session):
    projects_svc.create(session, name="A", client="Stari partner")
    assert suggestions.for_field(session, "client") == ["Stari partner"]
    suggestions.set_list(session, "client", ["  RIA ", "Western Union", "ria"])
    # dupli se sklanja, a upisana vrednost koja je izbačena iz liste se više ne nudi
    assert suggestions.for_field(session, "client") == ["RIA", "Western Union"]
    projects_svc.create(session, name="B", client="Novi partner")
    assert suggestions.for_field(session, "client")[-1] == "Novi partner"  # upisano se pamti
    suggestions.reset_list(session, "client")
    assert set(suggestions.for_field(session, "client")) == {"Stari partner", "Novi partner"}


def test_builtin_lists_and_order(session):
    phases = suggestions.for_field(session, "phase")
    assert phases[0] == "Inicijacija"
    suggestions.set_list(session, "phase", ["Dva", "Jedan"])
    assert suggestions.for_field(session, "phase") == ["Dva", "Jedan"]
    assert suggestions.is_custom(session, "phase")


def test_lists_editor_saves(qtbot, db):
    from app.ui.context import AppContext
    from app.ui.dialogs.lists_tab import ListsEditor

    ctx = AppContext(db)
    editor = ListsEditor(ctx, "client")
    qtbot.addWidget(editor)
    editor.new_item.setText("AlfaPay d.o.o.")
    editor.add()
    editor.new_item.setText("Banka Intesa")
    editor.add()
    editor.items.setCurrentRow(1)
    editor.move(-1)
    assert editor.current_values() == ["Banka Intesa", "AlfaPay d.o.o."]
    editor.which.setCurrentIndex(editor.which.findData("people"))
    editor.items.setCurrentRow(0)
    first = editor.current_values()[0]
    editor.remove()
    with db.session() as s:
        editor.save(s)
        s.commit()
    with db.session() as s:
        assert suggestions.for_field(s, "client") == ["Banka Intesa", "AlfaPay d.o.o."]
        assert first not in suggestions.for_field(s, "people")


def test_enter_adds_item_without_closing_settings(qtbot, db):
    from PySide6.QtCore import Qt

    from app.ui.context import AppContext
    from app.ui.dialogs.settings_dialog import SettingsDialog

    dlg = SettingsDialog(AppContext(db), None, tab="lists:client")
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.lists.new_item.setFocus()
    qtbot.keyClicks(dlg.lists.new_item, "RIA")
    qtbot.keyClick(dlg.lists.new_item, Qt.Key.Key_Return)
    assert dlg.isVisible() and dlg.lists.current_values() == ["RIA"]
