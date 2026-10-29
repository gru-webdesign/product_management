"""Šabloni: čuvanje trenutnog projekta kao šablona i brisanje sopstvenih šablona."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.services import projects as project_service
from app.services import templates as template_service
from app.ui import theme
from app.ui.context import AppContext

ROLE_ID = Qt.ItemDataRole.UserRole


def save_current_as_template(ctx: AppContext, parent=None) -> bool:
    pid = ctx.project_id
    if not pid:
        return False
    with ctx.session() as s:
        name = project_service.get(s, pid).name
    text, ok = QInputDialog.getText(
        parent,
        "Sačuvaj kao šablon",
        "Naziv šablona. Zadaci, zavisnosti, milestone-i i budžet se čuvaju bez statusa i "
        "troškova, a datumi kao razmak od početka projekta.",
        text=name,
    )
    if not ok or not text.strip():
        return False
    result = ctx.run(lambda s: template_service.save_from_project(s, pid, text).name, parent)
    if result:
        ctx.notify(f"Šablon „{result}“ je sačuvan. Biraš ga pri pravljenju novog projekta.")
    return bool(result)


class TemplatesDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Šabloni projekata")
        self.setMinimumSize(480, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        info = QLabel(
            "Šablon biraš u dijalogu „Novi projekat“. Ugrađeni šabloni ne mogu da se brišu."
        )
        info.setWordWrap(True)
        info.setProperty("muted", True)
        lay.addWidget(info)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        save = QPushButton("Sačuvaj trenutni projekat kao šablon")
        save.setEnabled(bool(ctx.project_id))
        save.clicked.connect(self._save)
        self.delete_button = QPushButton("Obriši")
        self.delete_button.setProperty("danger", True)
        self.delete_button.clicked.connect(self._delete)
        row.addWidget(save)
        row.addStretch(1)
        row.addWidget(self.delete_button)
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Zatvori")
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.list.currentItemChanged.connect(lambda *_: self._sync())
        self._load()

    def _load(self) -> None:
        self.list.clear()
        with self.ctx.session() as s:
            infos = template_service.list_templates(s)
        for i in infos:
            label = f"{i.name}\n{i.task_count} zadataka"
            if i.description:
                label += f". {i.description}"
            if i.builtin:
                label += "\nUgrađen"
            item = QListWidgetItem(label)
            item.setData(ROLE_ID, i.id)
            if i.builtin:
                item.setForeground(QColor(theme.tokens().muted))
            self.list.addItem(item)
        self._sync()

    def _sync(self) -> None:
        item = self.list.currentItem()
        tid = item.data(ROLE_ID) if item else ""
        self.delete_button.setEnabled(bool(tid) and not tid.startswith("builtin:"))

    def _save(self) -> None:
        if save_current_as_template(self.ctx, self):
            self._load()

    def _delete(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        tid = item.data(ROLE_ID)
        name = item.text().split("\n", 1)[0]
        if (
            QMessageBox.question(
                self,
                "Obriši šablon",
                f"Obrisati šablon „{name}“? Projekti napravljeni iz njega ostaju.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.ctx.run(lambda s: template_service.delete(s, tid), self)
        self._load()
