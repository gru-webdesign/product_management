"""Dijalog za planirani budžet projekta po kategorijama + upravljanje kategorijama."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.db.models import BudgetCategory
from app.labels import PROJECT_COLORS
from app.services import budget as budget_service
from app.services.money import format_money
from app.ui.context import AppContext
from app.ui.dialogs.base import FormDialog
from app.ui.sidebar import color_dot
from app.ui.widgets.fields import MoneyEdit

ROLE_ID = Qt.ItemDataRole.UserRole


class BudgetDialog(FormDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__("Budžet projekta", parent)
        self.ctx = ctx
        self.setMinimumSize(520, 460)
        info = QLabel("Planirani iznos po kategoriji, u osnovnoj valuti. Prazno = nije planirano.")
        info.setWordWrap(True)
        info.setProperty("muted", True)
        lay = QVBoxLayout()
        lay.addWidget(info)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Kategorija", "Planirano"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 180)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table, 1)
        self.total = QLabel()
        self.total.setProperty("heading", True)
        row = QHBoxLayout()
        for text, slot in (
            ("Nova kategorija", self._add),
            ("Preimenuj", self._rename),
            ("Obriši kategoriju", self._delete),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.total)
        lay.addLayout(row)
        self.root.insertLayout(0, lay, 1)
        self.edits: dict[str, MoneyEdit] = {}
        self._load()

    def _load(self, keep: dict[str, int] | None = None) -> None:
        with self.ctx.session() as s:
            cats = [(c.id, c.name, c.color) for c in budget_service.categories(s)]
            plan = budget_service.planned(s, self.ctx.project_id)
            self.base = budget_service.base_currency(s)
        if keep:
            plan.update(keep)
        self.table.setRowCount(len(cats))
        self.edits.clear()
        for r, (cid, name, color) in enumerate(cats):
            item = QTableWidgetItem(color_dot(color), name)
            item.setData(ROLE_ID, cid)
            self.table.setItem(r, 0, item)
            edit = MoneyEdit(plan.get(cid, 0))
            edit.textChanged.connect(lambda _t: self._update_total())
            self.table.setCellWidget(r, 1, edit)
            self.edits[cid] = edit
        self._update_total()

    def _current_values(self) -> dict[str, int]:
        return {cid: e.value_minor() for cid, e in self.edits.items() if e.is_valid()}

    def _update_total(self) -> None:
        self.total.setText(
            f"Ukupno: {format_money(sum(self._current_values().values()), self.base)}"
        )

    def _selected(self) -> tuple[str, str] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(ROLE_ID), item.text()

    def _add(self) -> None:
        name, ok = QInputDialog.getText(self, "Nova kategorija", "Naziv:")
        if ok and name.strip():
            keep = self._current_values()
            color = PROJECT_COLORS[len(self.edits) % len(PROJECT_COLORS)]
            if self.ctx.run(lambda s: budget_service.create_category(s, name, color), self):
                self._load(keep)

    def _rename(self) -> None:
        sel = self._selected()
        if not sel:
            return
        cid, old = sel
        name, ok = QInputDialog.getText(self, "Preimenuj kategoriju", "Naziv:", text=old)
        if ok and name.strip() and name != old:
            keep = self._current_values()
            self.ctx.run(
                lambda s: budget_service.rename_category(s, s.get(BudgetCategory, cid), name), self
            )
            self._load(keep)

    def _delete(self) -> None:
        sel = self._selected()
        if not sel:
            return
        cid, name = sel
        if (
            QMessageBox.question(
                self, "Obriši kategoriju", f"Obrisati kategoriju „{name}“ iz svih projekata?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        keep = self._current_values()
        keep.pop(cid, None)
        self.ctx.run(lambda s: budget_service.delete_category(s, s.get(BudgetCategory, cid)), self)
        self._load(keep)

    def validate(self) -> None:
        for e in self.edits.values():
            if not e.is_valid():
                raise ValueError(f"„{e.text()}“ nije ispravan iznos.")

    def save(self) -> bool:
        values = self._current_values()
        pid = self.ctx.project_id

        def work(s):
            for cid, amount in values.items():
                budget_service.set_planned(s, pid, cid, amount)
            return True

        return bool(self.ctx.run(work, self))


def edit_budget(ctx: AppContext, parent=None) -> bool:
    dlg = BudgetDialog(ctx, parent)
    if dlg.exec() == dlg.DialogCode.Accepted:
        return dlg.save()
    return False
