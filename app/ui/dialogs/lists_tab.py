"""Podešavanja → Liste: uređivanje predloga za padajuće liste (partneri, ljudi, faze...)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services import suggestions
from app.ui.context import AppContext

RESET = object()


class _EntryLine(QLineEdit):
    """Enter dodaje stavku i ne zatvara dijalog Podešavanja."""

    def keyPressEvent(self, event) -> None:  # noqa: N802
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            event.accept()


class ListsEditor(QWidget):
    """Jedna lista u isto vreme; izmene se pamte za sve liste i čuvaju se dugmetom Sačuvaj."""

    def __init__(self, ctx: AppContext, start: str = "client") -> None:
        super().__init__()
        self.ctx = ctx
        self.lists: dict[str, list[str]] = {}
        self.changed: dict[str, object] = {}  # naziv → nova lista ili RESET
        self._current = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 14, 4, 4)
        root.setSpacing(10)

        self.which = QComboBox()
        for info in suggestions.LISTS.values():
            self.which.addItem(info.title, info.key)
        self.hint = QLabel()
        self.hint.setProperty("faint", True)
        self.hint.setWordWrap(True)
        root.addWidget(self.which)
        root.addWidget(self.hint)

        add_row = QHBoxLayout()
        self.new_item = _EntryLine()
        self.new_item.setPlaceholderText("Nova stavka, pa Enter")
        self.new_item.returnPressed.connect(self.add)
        add = QPushButton("Dodaj")
        add.clicked.connect(self.add)
        add_row.addWidget(self.new_item, 1)
        add_row.addWidget(add)
        root.addLayout(add_row)

        body = QHBoxLayout()
        self.items = QListWidget()
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.items.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.items.setMinimumHeight(260)
        self.items.setSpacing(2)
        self.items.itemChanged.connect(self._touch)
        self.items.model().rowsMoved.connect(self._touch)
        body.addWidget(self.items, 1)
        side = QVBoxLayout()
        for text, slot in (
            ("Ukloni", self.remove),
            ("Gore", lambda: self.move(-1)),
            ("Dole", lambda: self.move(1)),
            ("Abecedno", self.sort),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            side.addWidget(b)
        side.addStretch(1)
        self.reset_button = QPushButton("Podrazumevano")
        self.reset_button.setToolTip("Vrati ugrađenu listu za ovo polje")
        self.reset_button.clicked.connect(self.reset)
        side.addWidget(self.reset_button)
        body.addLayout(side)
        root.addLayout(body)
        tip = QLabel(
            "Dupli klik menja naziv, a redosled menjaš prevlačenjem. Uklonjena stavka se više ne "
            "nudi, ali ostaje upisana tamo gde je već korišćena."
        )
        tip.setWordWrap(True)
        tip.setProperty("faint", True)
        root.addWidget(tip)

        self.which.currentIndexChanged.connect(self._show)
        self.which.setCurrentIndex(max(0, self.which.findData(start)))
        self._show()

    # --- prikaz ---
    def _load(self, name: str) -> list[str]:
        if name not in self.lists:
            with self.ctx.session() as s:
                self.lists[name] = suggestions.get_list(s, name)
        return self.lists[name]

    def _show(self) -> None:
        self._store()
        name = self.which.currentData()
        self._current = name
        self.hint.setText(suggestions.LISTS[name].hint)
        self._fill(self._load(name))

    def _fill(self, values: list[str]) -> None:
        self.items.blockSignals(True)
        self.items.clear()
        for v in values:
            item = QListWidgetItem(v)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.items.addItem(item)
        self.items.blockSignals(False)

    def current_values(self) -> list[str]:
        return [self.items.item(i).text() for i in range(self.items.count())]

    def _store(self) -> None:
        if self._current and self.changed.get(self._current) not in (None, RESET):
            self.changed[self._current] = self.current_values()
            self.lists[self._current] = self.current_values()

    def _touch(self, *_):
        if self._current:
            self.changed[self._current] = self.current_values()
            self.lists[self._current] = self.current_values()

    # --- izmene ---
    def add(self) -> None:
        text = " ".join(self.new_item.text().split())
        if not text:
            return
        existing = [v.casefold() for v in self.current_values()]
        if text.casefold() in existing:
            self.items.setCurrentRow(existing.index(text.casefold()))
        else:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.items.addItem(item)
            self.items.setCurrentItem(item)
            self._touch()
        self.new_item.clear()

    def remove(self) -> None:
        rows = sorted((self.items.row(i) for i in self.items.selectedItems()), reverse=True)
        for row in rows:
            self.items.takeItem(row)
        if rows:
            self._touch()

    def move(self, step: int) -> None:
        row = self.items.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < self.items.count():
            return
        item = self.items.takeItem(row)
        self.items.insertItem(target, item)
        self.items.setCurrentRow(target)
        self._touch()

    def sort(self) -> None:
        self._fill(sorted(self.current_values(), key=str.casefold))
        self._touch()

    def reset(self) -> None:
        name = self._current
        info = suggestions.LISTS[name]
        with self.ctx.session() as s:
            used = suggestions.used_values(s, name)
        known = {b.casefold() for b in info.builtin}
        values = [
            *info.builtin,
            *sorted((u for u in used if u.casefold() not in known), key=str.casefold),
        ]
        self.lists[name] = values
        self.changed[name] = RESET
        self._fill(values)

    # --- čuvanje ---
    def save(self, session) -> None:
        """Poziva se iz SettingsDialog._save (u istoj transakciji)."""
        self._store()
        for name, value in self.changed.items():
            if value is RESET:
                suggestions.reset_list(session, name)
            else:
                suggestions.set_list(session, name, value)
