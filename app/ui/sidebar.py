"""Leva traka: naziv aplikacije, lista projekata, arhiva i podešavanja."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
)

from app import APP_NAME
from app.services import projects as project_service
from app.ui import icons
from app.ui.context import AppContext
from app.ui.dialogs.project_dialog import ProjectDialog

ROLE_ID = Qt.ItemDataRole.UserRole


def color_dot(color: str, size: int = 10, faded: bool = False) -> QIcon:
    px = QPixmap(size * 2, size * 2)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    if faded:
        c.setAlpha(110)
    p.setBrush(c)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(4, 4, size * 2 - 8, size * 2 - 8, 5, 5)
    p.end()
    px.setDevicePixelRatio(2)
    return QIcon(px)


class Sidebar(QFrame):
    settings_requested = Signal()

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Sidebar")
        self.setFixedWidth(248)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 16, 14, 12)
        lay.setSpacing(8)

        name = QLabel(APP_NAME)
        name.setObjectName("AppName")
        lay.addWidget(name)
        lay.addSpacing(10)

        head = QHBoxLayout()
        title = QLabel("PROJEKTI")
        title.setObjectName("SidebarTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.add_button = QToolButton()
        self.add_button.setIcon(icons.icon("plus"))
        self.add_button.setToolTip("Novi projekat (Ctrl+Shift+N)")
        self.add_button.clicked.connect(self.new_project)
        head.addWidget(self.add_button)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("ProjectList")
        self.list.setIconSize(QSize(10, 10))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.currentItemChanged.connect(self._current_changed)
        self.list.itemDoubleClicked.connect(lambda _i: self.edit_current())
        lay.addWidget(self.list, 1)

        self.show_archived = QCheckBox("Prikaži arhivirane")
        self.show_archived.toggled.connect(lambda _c: self.reload())
        lay.addWidget(self.show_archived)

        settings = QToolButton()
        settings.setIcon(icons.icon("settings"))
        settings.setText("  Podešavanja")
        settings.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        settings.clicked.connect(self.settings_requested.emit)
        lay.addWidget(settings, 0, Qt.AlignmentFlag.AlignLeft)

        ctx.data_changed.connect(self.reload)
        self.reload()

    # --- podaci ----------------------------------------------------------------------------------

    def reload(self) -> None:
        current = self.ctx.project_id
        self.list.blockSignals(True)
        self.list.clear()
        with self.ctx.session() as s:
            rows = []
            for p in project_service.list_projects(s, self.show_archived.isChecked()):
                done, total, pct = project_service.progress(s, p.id)
                rows.append((p.id, p.name, p.color, p.archived, total, pct))
        for pid, name, color, archived, total, pct in rows:
            item = QListWidgetItem(color_dot(color, faded=archived), name)
            item.setData(ROLE_ID, pid)
            item.setToolTip(f"{name}\n{total} zadataka · {pct}% završeno")
            if archived:
                item.setForeground(QColor(self.palette().placeholderText().color()))
            self.list.addItem(item)
        self.list.blockSignals(False)

        ids = [r[0] for r in rows]
        if current in ids:
            self.list.setCurrentRow(ids.index(current))
        elif ids:
            self.list.setCurrentRow(0)
            self.ctx.select_project(ids[0])
        else:
            self.ctx.select_project("")

    def _current_changed(self, item: QListWidgetItem | None, _prev) -> None:
        self.ctx.select_project(item.data(ROLE_ID) if item else "")

    def select(self, project_id: str) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(ROLE_ID) == project_id:
                self.list.setCurrentRow(row)
                return

    # --- akcije ----------------------------------------------------------------------------------

    def new_project(self) -> None:
        dlg = ProjectDialog(parent=self.window())
        if dlg.exec():
            values = dlg.values()
            project = self.ctx.run(lambda s: project_service.create(s, **values).id, self.window())
            if project:
                self.ctx.select_project(project)
                self.select(project)
                self.ctx.notify(f"Projekat „{values['name']}“ je napravljen.")

    def edit_current(self) -> None:
        pid = self.ctx.project_id
        if not pid:
            return
        with self.ctx.session() as s:
            project = project_service.get(s, pid)
        dlg = ProjectDialog(project, parent=self.window())
        if dlg.exec():
            values = dlg.values()
            self.ctx.run(
                lambda s: project_service.update(s, project_service.get(s, pid), **values),
                self.window(),
            )

    def toggle_archive_current(self) -> None:
        pid = self.ctx.project_id
        if not pid:
            return

        def work(s):
            p = project_service.get(s, pid)
            project_service.set_archived(s, p, not p.archived)
            return p.archived

        archived = self.ctx.run(work, self.window())
        self.ctx.notify("Projekat je arhiviran." if archived else "Projekat je vraćen iz arhive.")

    def delete_current(self) -> None:
        pid = self.ctx.project_id
        if not pid:
            return
        with self.ctx.session() as s:
            p = project_service.get(s, pid)
            name, count = p.name, len(p.tasks)
        answer = QMessageBox.question(
            self.window(),
            "Obriši projekat",
            f"Obrisati projekat „{name}“ sa {count} zadataka, troškovima i linkovima?\n\n"
            "Ovo ne može da se poništi (osim vraćanjem iz automatske kopije baze).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.ctx.project_id = ""
            self.ctx.run(lambda s: project_service.delete(s, project_service.get(s, pid)))
            self.ctx.notify(f"Projekat „{name}“ je obrisan.")

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item:
            return
        self.list.setCurrentItem(item)
        with self.ctx.session() as s:
            archived = project_service.get(s, item.data(ROLE_ID)).archived
        menu = QMenu(self)
        menu.addAction(icons.icon("edit"), "Uredi projekat…", self.edit_current)
        menu.addAction(
            icons.icon("archive"),
            "Vrati iz arhive" if archived else "Arhiviraj",
            self.toggle_archive_current,
        )
        menu.addSeparator()
        menu.addAction(icons.icon("trash"), "Obriši…", self.delete_current)
        menu.exec(self.list.mapToGlobal(pos))
