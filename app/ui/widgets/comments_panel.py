"""Komentari gledalaca sa linka za deljenje (za ceo projekat ili jedan zadatak)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.db.models import RemoteComment
from app.services import sharing
from app.share.client import ShareError
from app.ui import icons, theme
from app.ui.context import AppContext

ROLE_ID = Qt.ItemDataRole.UserRole


class CommentsPanel(QWidget):
    def __init__(self, ctx: AppContext, task_id: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.task_id = task_id
        self.project_id = ctx.project_id
        if task_id:
            from app.db.models import Task

            with ctx.session() as s:
                task = s.get(Task, task_id)
                self.project_id = task.project_id if task else ctx.project_id
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.show_resolved = QCheckBox("Prikaži rešene")
        self.show_resolved.toggled.connect(lambda _c: self.reload())
        top.addWidget(self.show_resolved)
        top.addStretch(1)
        self.sync_button = QPushButton("Preuzmi nove")
        self.sync_button.setIcon(icons.icon("refresh"))
        self.sync_button.clicked.connect(self.sync)
        top.addWidget(self.sync_button)
        lay.addLayout(top)

        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setSpacing(2)
        self.list.itemSelectionChanged.connect(self._selection)
        lay.addWidget(self.list, 1)

        bottom = QHBoxLayout()
        self.status = QLabel()
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.resolve_button = QPushButton("Označi kao rešeno")
        self.resolve_button.setIcon(icons.icon("check"))
        self.resolve_button.setEnabled(False)
        self.resolve_button.clicked.connect(self.toggle_resolved)
        bottom.addWidget(self.resolve_button)
        lay.addLayout(bottom)
        self.reload()

    def reload(self) -> None:
        t = theme.tokens()
        with self.ctx.session() as s:
            rows = [
                (
                    c.id,
                    c.author_name,
                    c.posted_at,
                    c.text,
                    c.task.title if c.task else "",
                    c.resolved,
                    c.read,
                )
                for c in sharing.comments(
                    s,
                    self.project_id,
                    self.task_id,
                    include_resolved=self.show_resolved.isChecked(),
                )
            ]
            sharing.mark_read(s, self.project_id, self.task_id)
            s.commit()
            has_link = sharing.active_link(s, self.project_id) is not None
        self.list.clear()
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        for cid, author, when, text, task, resolved, read in rows:
            head = f"{author}   ·   {when.astimezone().strftime('%d.%m.%Y. %H:%M')}"
            if task and not self.task_id:
                head += f"   ·   {task}"
            if resolved:
                head += "   ·   rešeno"
            elif not read:
                head += "   ·   novo"
            item = QListWidgetItem(f"{head}\n{text}")
            item.setData(ROLE_ID, cid)
            if resolved:
                item.setForeground(QColor(t.faint))
            self.list.addItem(item)
        if not rows:
            empty = QListWidgetItem(
                "Još nema komentara."
                if has_link
                else "Komentari stižu kad podeliš projekat linkom (dugme „Podeli“)."
            )
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(QColor(t.faint))
            self.list.addItem(empty)
        self.sync_button.setEnabled(has_link)
        self._selection()

    def _selection(self) -> None:
        item = self.list.currentItem()
        cid = item.data(ROLE_ID) if item else None
        self.resolve_button.setEnabled(bool(cid))
        if cid:
            with self.ctx.session() as s:
                c = s.get(RemoteComment, cid)
                self.resolve_button.setText(
                    "Vrati kao nerešeno" if c and c.resolved else "Označi kao rešeno"
                )

    def toggle_resolved(self) -> None:
        item = self.list.currentItem()
        cid = item.data(ROLE_ID) if item else None
        if not cid:
            return
        with self.ctx.session() as s:
            c = s.get(RemoteComment, cid)
            sharing.set_resolved(s, c, not c.resolved)
            s.commit()
        self.reload()
        self.ctx.data_changed.emit()

    def sync(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with self.ctx.session() as s:
                link = sharing.active_link(s, self.project_id)
                if link is None:
                    return
                with sharing.make_client(s) as client:
                    n = sharing.sync_comments(s, client, link)
                s.commit()
            self.status.setText(f"Preuzeto novih: {n}." if n else "Nema novih komentara.")
        except ShareError as exc:
            self.status.setText(str(exc))
        finally:
            QApplication.restoreOverrideCursor()
        self.reload()
        self.ctx.data_changed.emit()
