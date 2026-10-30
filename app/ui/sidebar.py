"""Leva traka: naziv aplikacije, lista projekata, arhiva i podešavanja."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
)

from app import APP_NAME
from app.services import projects as project_service
from app.ui import icons, theme
from app.ui.context import AppContext
from app.ui.dialogs.project_dialog import ProjectDialog

ROLE_ID = Qt.ItemDataRole.UserRole
ICON_PATH = Path(__file__).resolve().parents[1] / "resources" / "icons" / "app-256.png"


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


ROLE_COLOR = Qt.ItemDataRole.UserRole + 1
ROLE_PCT = Qt.ItemDataRole.UserRole + 2
ROLE_ARCHIVED = Qt.ItemDataRole.UserRole + 3


class ProjectDelegate(QStyledItemDelegate):
    """Red projekta: obojeni kvadratić, naziv i tanka traka napretka sa procentom."""

    def sizeHint(self, option, index) -> QSize:
        return QSize(180, 50)

    def paint(self, p: QPainter, option, index) -> None:
        t = theme.tokens()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(0, 2, 0, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.sidebar_active if selected else t.sidebar_hover))
            p.drawRoundedRect(r, 8, 8)
        archived = bool(index.data(ROLE_ARCHIVED))
        color = QColor(index.data(ROLE_COLOR) or t.accent)
        if archived:
            color.setAlpha(110)
        pct = int(index.data(ROLE_PCT) or 0)
        x = r.left() + 10
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(x, r.top() + 11, 9, 9), 3, 3)

        name_color = QColor("#FFFFFF" if selected else t.sidebar_text)
        if archived:
            name_color = QColor(t.sidebar_muted)
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Medium)
        p.setFont(font)
        p.setPen(name_color)
        text_rect = QRectF(x + 18, r.top() + 4, r.width() - 40, 22)
        name = QFontMetrics(font).elidedText(
            index.data(Qt.ItemDataRole.DisplayRole),
            Qt.TextElideMode.ElideRight,
            int(text_rect.width()),
        )
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)

        small = QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() - 1.5))
        p.setFont(small)
        p.setPen(QColor(t.sidebar_muted))
        pct_rect = QRectF(r.right() - 44, r.top() + 24, 36, 16)
        p.drawText(pct_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{pct}%")
        track = QRectF(x + 18, r.top() + 31, r.width() - 82, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.sidebar_border if not selected else t.sidebar_hover))
        p.drawRoundedRect(track, 2, 2)
        if pct:
            fill = QRectF(track)
            fill.setWidth(max(4.0, track.width() * pct / 100))
            p.setBrush(color)
            p.drawRoundedRect(fill, 2, 2)
        p.restore()


class Sidebar(QFrame):
    settings_requested = Signal()
    theme_toggle_requested = Signal()

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Sidebar")
        self.setFixedWidth(256)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 18, 14, 12)
        lay.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo_px = QPixmap(str(ICON_PATH))
        logo_px.setDevicePixelRatio(logo_px.width() / 34)
        logo.setPixmap(logo_px)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("AppName")
        tagline = QLabel("Projekti, rokovi i budžet")
        tagline.setObjectName("AppTagline")
        names.addWidget(name)
        names.addWidget(tagline)
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(18)

        self.dashboard_button = QToolButton()
        self.dashboard_button.setObjectName("NavButton")
        self.dashboard_button.setText("  Pregled")
        self.dashboard_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.dashboard_button.setCheckable(True)
        self.dashboard_button.setToolTip("Pregled svih projekata (Ctrl+0)")
        self.dashboard_button.clicked.connect(lambda: self.ctx.show_dashboard.emit())
        self.dashboard_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(self.dashboard_button)
        lay.addSpacing(14)
        self.dashboard_mode = False
        ctx.show_dashboard.connect(self._enter_dashboard)

        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 0, 0)
        title = QLabel("Projekti")
        title.setObjectName("SidebarTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.add_button = QToolButton()
        self.add_button.setToolTip("Novi projekat (Ctrl+Shift+N)")
        self.add_button.clicked.connect(self.new_project)
        head.addWidget(self.add_button)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("ProjectList")
        self.list.setItemDelegate(ProjectDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setUniformItemSizes(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.currentItemChanged.connect(self._current_changed)
        self.list.itemDoubleClicked.connect(lambda _i: self.edit_current())
        lay.addWidget(self.list, 1)

        self.show_archived = QCheckBox("Prikaži arhivirane")
        self.show_archived.toggled.connect(lambda _c: self.reload())
        lay.addWidget(self.show_archived)

        footer = QFrame()
        footer.setObjectName("SidebarFooter")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(0, 10, 0, 0)
        foot.setSpacing(4)
        self.settings_button = QToolButton()
        self.settings_button.setText("  Podešavanja")
        self.settings_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.settings_button.clicked.connect(self.settings_requested.emit)
        foot.addWidget(self.settings_button)
        foot.addStretch(1)
        self.theme_button = QToolButton()
        self.theme_button.clicked.connect(self.theme_toggle_requested.emit)
        foot.addWidget(self.theme_button)
        lay.addSpacing(6)
        lay.addWidget(footer)

        ctx.data_changed.connect(self.reload)
        theme.manager().changed.connect(self._theme_changed)
        self._theme_changed()
        self.reload()

    def _theme_changed(self) -> None:
        t = theme.tokens()
        self.dashboard_button.setIcon(icons.icon("dashboard", t.sidebar_text))
        self.add_button.setIcon(icons.icon("plus", t.sidebar_muted))
        self.settings_button.setIcon(icons.icon("settings", t.sidebar_muted))
        dark = t.name == "dark"
        self.theme_button.setIcon(icons.icon("sun" if dark else "moon", t.sidebar_muted))
        self.theme_button.setToolTip("Svetla tema" if dark else "Tamna tema")
        self.list.viewport().update()

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
            item = QListWidgetItem(name)
            item.setData(ROLE_ID, pid)
            item.setData(ROLE_COLOR, color)
            item.setData(ROLE_PCT, pct)
            item.setData(ROLE_ARCHIVED, archived)
            item.setToolTip(f"{name}\n{total} zadataka, {pct}% završeno")
            self.list.addItem(item)
        self.list.blockSignals(False)

        ids = [r[0] for r in rows]
        if self.dashboard_mode:
            if current not in ids:
                self.ctx.project_id = ""
            return
        if current in ids:
            self.list.setCurrentRow(ids.index(current))
        elif ids:
            self.list.setCurrentRow(0)
            self.ctx.select_project(ids[0])
        else:
            self.ctx.select_project("")

    def _current_changed(self, item: QListWidgetItem | None, _prev) -> None:
        if item is None:
            if not self.dashboard_mode:
                self.ctx.select_project("")
            return
        self._leave_dashboard()
        self.ctx.open_project(item.data(ROLE_ID))

    def _enter_dashboard(self) -> None:
        self.dashboard_mode = True
        self.dashboard_button.setChecked(True)
        self.list.blockSignals(True)
        self.list.setCurrentRow(-1)
        self.list.clearSelection()
        self.list.blockSignals(False)

    def _leave_dashboard(self) -> None:
        self.dashboard_mode = False
        self.dashboard_button.setChecked(False)

    def select(self, project_id: str) -> None:
        self._leave_dashboard()
        for row in range(self.list.count()):
            if self.list.item(row).data(ROLE_ID) == project_id:
                self.list.setCurrentRow(row)
                return

    # --- akcije ----------------------------------------------------------------------------------

    def new_project(self) -> None:
        from datetime import date

        from app.services import templates as template_service

        with self.ctx.session() as s:
            infos = template_service.list_templates(s)
        dlg = ProjectDialog(parent=self.window(), templates=infos)
        if dlg.exec():
            values = dlg.values()
            template_id = dlg.template_id()

            def work(s):
                p = project_service.create(s, **values)
                if template_id:
                    data = template_service.get_data(s, template_id)
                    template_service.apply(s, p.id, data, values["start_date"] or date.today())
                return p.id

            project = self.ctx.run(work, self.window())
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
