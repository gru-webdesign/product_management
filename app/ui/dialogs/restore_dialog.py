"""Vraćanje baze iz automatske kopije. Trenutno stanje se pre toga i samo sačuva kao kopija."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from app.services import backup
from app.services.defaults import ensure_defaults
from app.ui.context import AppContext


def _label(path) -> str:
    stem = path.stem.removeprefix(backup.PREFIX)
    try:
        when = datetime.strptime(stem[:15], "%Y%m%d-%H%M%S")
        return when.strftime("%d.%m.%Y.  %H:%M:%S") + f"    ({path.stat().st_size // 1024} KB)"
    except ValueError:
        return path.name


class RestoreDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Vrati bazu iz kopije")
        self.setMinimumSize(440, 360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        info = QLabel(
            "Kopija se pravi automatski pri svakom pokretanju (čuva se poslednjih 10). "
            "Pre vraćanja, trenutno stanje se sačuva kao nova kopija."
        )
        info.setWordWrap(True)
        info.setProperty("muted", True)
        lay.addWidget(info)

        self.list = QListWidget()
        for path in backup.list_backups(ctx.db.paths):
            item = QListWidgetItem(_label(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        lay.addWidget(self.list, 1)

        buttons = QDialogButtonBox()
        self.restore_button = buttons.addButton("Vrati", QDialogButtonBox.ButtonRole.AcceptRole)
        self.restore_button.setProperty("primary", True)
        self.restore_button.setEnabled(self.list.count() > 0)
        buttons.addButton("Zatvori", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.restore)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def restore(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        answer = QMessageBox.question(
            self,
            "Vrati bazu",
            f"Zameniti sve trenutne podatke kopijom od {item.text().split('    ')[0]}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        from pathlib import Path

        db = self.ctx.db
        backup.create_backup(db.paths)
        db.dispose()
        backup.restore_backup(db.paths, Path(item.data(Qt.ItemDataRole.UserRole)))
        db.upgrade()
        with db.session() as s:
            ensure_defaults(s)
            s.commit()
        self.ctx.project_id = ""
        self.ctx.data_changed.emit()
        self.ctx.notify("Baza je vraćena iz kopije.")
        self.accept()
