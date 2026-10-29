"""Pregled svih projekata: brojke na vrhu, tabela projekata, rokovi i sati ove nedelje."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services import dashboard
from app.services.gantt_math import MONTHS
from app.services.timetracking import format_hours
from app.ui import theme
from app.ui.context import AppContext
from app.ui.sidebar import color_dot
from app.ui.widgets.paint import PillDelegate, ProgressDelegate

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_TASK = Qt.ItemDataRole.UserRole + 5
WEEKDAYS_FULL = ["ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota", "nedelja"]


def long_date(d: date) -> str:
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day}. {MONTHS[d.month - 1]}"


class Stat(QFrame):
    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(2)
        self.value = QLabel("0")
        self.value.setObjectName("KpiValue")
        self.label = QLabel(label)
        self.label.setObjectName("KpiLabel")
        lay.addWidget(self.value)
        lay.addWidget(self.label)

    def set(self, value: str, color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")


class HoursBars(QWidget):
    """Sati po projektu ove nedelje: naziv, traka (bez pozadinske staze) i broj."""

    ROW = 26

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows: list[tuple[str, str, float]] = []

    def set_rows(self, rows: list[tuple[str, str, float]]) -> None:
        self.rows = rows
        self.setFixedHeight(max(1, len(rows)) * self.ROW + 4)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(280, max(1, len(self.rows)) * self.ROW + 4)

    def paintEvent(self, _e) -> None:
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.rows:
            p.setPen(QColor(t.faint))
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "Ove nedelje još nema upisanog vremena.",
            )
            return
        peak = max(h for *_, h in self.rows) or 1
        name_w, num_w = int(self.width() * 0.42), 70
        bar_w = self.width() - name_w - num_w - 12
        for i, (name, color, hours) in enumerate(self.rows):
            y = i * self.ROW
            p.setPen(QColor(t.text))
            p.setFont(self.font())
            p.drawText(
                QRectF(0, y, name_w - 8, self.ROW),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, name_w - 8),
            )
            w = max(3.0, bar_w * hours / peak)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(name_w, y + self.ROW / 2 - 4, w, 8), 3, 3)
            p.setPen(QColor(t.muted))
            p.drawText(
                QRectF(self.width() - num_w, y, num_w, self.ROW),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                format_hours(hours),
            )


class DashboardView(QWidget):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 22, 28, 24)
        root.setSpacing(18)

        head = QVBoxLayout()
        head.setSpacing(2)
        title = QLabel("Pregled")
        title.setObjectName("ProjectTitle")
        self.date_label = QLabel()
        self.date_label.setProperty("muted", True)
        head.addWidget(title)
        head.addWidget(self.date_label)
        root.addLayout(head)

        stats = QGridLayout()
        stats.setSpacing(12)
        self.s_projects = Stat("aktivnih projekata")
        self.s_open = Stat("otvorenih zadataka")
        self.s_late = Stat("zadataka kasni")
        self.s_hours = Stat("sati ove nedelje")
        for i, s in enumerate((self.s_projects, self.s_open, self.s_late, self.s_hours)):
            stats.addWidget(s, 0, i)
        root.addLayout(stats)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(8)
        h = QLabel("Projekti")
        h.setProperty("heading", True)
        left.addWidget(h)
        self.projects = QTreeWidget()
        self.projects.setHeaderLabels(
            ["Projekat", "Napredak", "Budžet", "Kasni", "Sledeći milestone", "Komentari"]
        )
        self.projects.setRootIsDecorated(False)
        self.projects.setUniformRowHeights(True)
        self.projects.setIconSize(QSize(10, 10))
        self.projects.setItemDelegateForColumn(1, ProgressDelegate(self.projects))
        self.projects.setItemDelegateForColumn(2, PillDelegate(self.projects))
        ph = self.projects.header()
        ph.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, w in ((1, 124), (2, 104), (3, 52), (4, 176), (5, 78)):
            ph.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.projects.setColumnWidth(col, w)
        self.projects.itemClicked.connect(self._open_project)
        self.projects.setCursor(Qt.CursorShape.PointingHandCursor)
        left.addWidget(self.projects, 1)
        cols.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(8)
        h = QLabel("Rokovi u narednih 14 dana")
        h.setProperty("heading", True)
        right.addWidget(h)
        self.deadlines = QTreeWidget()
        self.deadlines.setHeaderHidden(True)
        self.deadlines.setColumnCount(3)
        self.deadlines.setRootIsDecorated(False)
        self.deadlines.setIconSize(QSize(10, 10))
        self.deadlines.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.deadlines.setColumnWidth(0, 78)
        self.deadlines.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.deadlines.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.deadlines.setColumnWidth(2, 120)
        self.deadlines.header().setStretchLastSection(False)
        self.deadlines.itemClicked.connect(self._open_deadline)
        self.deadlines.setCursor(Qt.CursorShape.PointingHandCursor)
        right.addWidget(self.deadlines, 1)
        h2 = QLabel("Sati ove nedelje")
        h2.setProperty("heading", True)
        right.addSpacing(6)
        right.addWidget(h2)
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        self.hours = HoursBars()
        cl.addWidget(self.hours)
        right.addWidget(card)
        cols.addLayout(right, 3)
        root.addLayout(cols, 1)

        ctx.data_changed.connect(self._maybe_reload)
        ctx.timer_changed.connect(self._maybe_reload)
        theme.manager().changed.connect(self._maybe_reload)

    def _maybe_reload(self) -> None:
        if self.isVisible():
            self.reload()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
        t = theme.tokens()
        with self.ctx.session() as s:
            ov = dashboard.build(s)
        self.date_label.setText(long_date(ov.today).capitalize())
        self.s_projects.set(str(len(ov.projects)))
        self.s_open.set(str(ov.open_tasks))
        self.s_late.set(str(ov.overdue_tasks), t.danger if ov.overdue_tasks else None)
        self.s_hours.set(format_hours(ov.hours_this_week) if ov.hours_this_week else "0 h")

        self.projects.clear()
        mono = theme.mono(self.projects.font(), -0.5)
        for c in ov.projects:
            label = c.name + (f"\n{c.client}" if c.client else "")
            item = QTreeWidgetItem([c.name, "", "", "", "", ""])
            item.setIcon(0, color_dot(c.color))
            item.setData(0, ROLE_ID, c.id)
            item.setToolTip(0, label)
            item.setData(1, ProgressDelegate.VALUE_ROLE, c.progress)
            if c.has_budget:
                text, color = {
                    "over": ("Prekoračen", t.danger),
                    "warn": (f"{c.budget_percent}%", t.warning),
                }.get(c.budget_state, (f"{c.budget_percent}%", t.success))
            else:
                text, color = "Nije postavljen", t.faint
            item.setText(2, text)
            item.setData(2, PillDelegate.COLOR_ROLE, color)
            item.setText(3, str(c.overdue) if c.overdue else "")
            item.setForeground(3, QColor(t.danger))
            item.setFont(3, mono)
            if c.next_milestone:
                item.setText(4, f"{c.next_milestone_date.strftime('%d.%m.')}  {c.next_milestone}")
            item.setText(5, f"{c.unread} novih" if c.unread else "")
            item.setForeground(5, QColor(t.accent))
            self.projects.addTopLevelItem(item)
        self.projects.setColumnHidden(5, not any(c.unread for c in ov.projects))
        if not ov.projects:
            empty = QTreeWidgetItem(["Nema aktivnih projekata. Napravi prvi u levoj traci."])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(0, QColor(t.faint))
            self.projects.addTopLevelItem(empty)

        self.deadlines.clear()
        for d in ov.deadlines:
            item = QTreeWidgetItem([dashboard.relative_day(d.days), d.title, d.project_name])
            item.setData(0, ROLE_ID, d.project_id)
            item.setData(0, ROLE_TASK, d.task_id)
            item.setToolTip(1, f"{d.title}\n{d.project_name}, rok {d.due.strftime('%d.%m.%Y.')}")
            item.setForeground(
                0, QColor(t.danger if d.overdue else (t.warning if d.days <= 1 else t.muted))
            )
            item.setForeground(2, QColor(t.muted))
            item.setIcon(2, color_dot(d.project_color))
            self.deadlines.addTopLevelItem(item)
        if not ov.deadlines:
            empty = QTreeWidgetItem(["", "Nema rokova u narednih 14 dana."])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(1, QColor(t.faint))
            self.deadlines.addTopLevelItem(empty)
        self.hours.set_rows([(name, color, h) for _pid, name, color, h in ov.week_hours])

    def _open_project(self, item: QTreeWidgetItem) -> None:
        pid = item.data(0, ROLE_ID)
        if pid:
            QTimer.singleShot(0, lambda: self.ctx.open_project(pid))

    def _open_deadline(self, item: QTreeWidgetItem) -> None:
        pid, tid = item.data(0, ROLE_ID), item.data(0, ROLE_TASK)
        if pid:

            def go():
                self.ctx.open_project(pid)
                if tid:
                    self.ctx.open_task_requested.emit(tid)

            QTimer.singleShot(0, go)
