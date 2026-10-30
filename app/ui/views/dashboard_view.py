"""Pregled svih projekata u karticama: brojke, projekti, stanje, rokovi, aktivnost i sati."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.db.models import TaskStatus
from app.labels import TASK_STATUS
from app.services import dashboard
from app.services.gantt_math import MONTHS
from app.services.timetracking import format_hours
from app.ui import theme
from app.ui.context import AppContext
from app.ui.sidebar import color_dot
from app.ui.widgets.card import Card
from app.ui.widgets.kpi import IconChip, KpiCard
from app.ui.widgets.paint import PillDelegate, ProgressDelegate

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_TASK = Qt.ItemDataRole.UserRole + 5
WEEKDAYS_FULL = ["ponedeljak", "utorak", "sreda", "četvrtak", "petak", "subota", "nedelja"]
WEEKDAYS_SHORT = ["P", "U", "S", "Č", "P", "S", "N"]
MONTHS_SHORT = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"]


def long_date(d: date) -> str:
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day}. {MONTHS[d.month - 1]}"


def greeting(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if 5 <= hour < 12:
        return "Dobro jutro"
    if 12 <= hour < 18:
        return "Dobar dan"
    return "Dobro veče"


def status_colors() -> dict[TaskStatus, str]:
    t = theme.tokens()
    return {
        TaskStatus.TODO: t.faint,
        TaskStatus.IN_PROGRESS: t.accent,
        TaskStatus.REVIEW: t.warning,
        TaskStatus.DONE: t.success,
    }


class ProgressRing(QWidget):
    """Prsten sa udelom zadataka po statusu i procentom završenog u sredini."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.counts: dict[TaskStatus, int] = {}
        self.percent = 0
        self.setFixedSize(156, 156)

    def set_data(self, counts: dict[TaskStatus, int], percent: int) -> None:
        self.counts, self.percent = counts, percent
        self.update()

    def paintEvent(self, _e) -> None:
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = 14.0
        r = QRectF(self.rect()).adjusted(
            width / 2 + 2, width / 2 + 2, -width / 2 - 2, -width / 2 - 2
        )
        pen = QPen(QColor(t.surface_alt), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawEllipse(r)
        total = sum(self.counts.values())
        if total:
            start = 90 * 16
            gap = 2 * 16 if sum(1 for n in self.counts.values() if n) > 1 else 0
            colors = status_colors()
            for status in (TaskStatus.DONE, TaskStatus.REVIEW, TaskStatus.IN_PROGRESS):
                n = self.counts.get(status, 0)
                if not n:
                    continue
                span = int(-360 * 16 * n / total)
                pen = QPen(QColor(colors[status]), width, Qt.PenStyle.SolidLine)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(r, start - gap // 2, span + gap)
                start += span
        p.setPen(QColor(t.text))
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() + 11)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        center = QRectF(self.rect())
        p.drawText(
            center.adjusted(0, -14, 0, -14), Qt.AlignmentFlag.AlignCenter, f"{self.percent}%"
        )
        f2 = QFont(self.font())
        f2.setPointSizeF(f2.pointSizeF() - 1)
        p.setFont(f2)
        p.setPen(QColor(t.muted))
        p.drawText(center.adjusted(0, 26, 0, 26), Qt.AlignmentFlag.AlignCenter, "završeno")


class LegendRow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        self.name = QLabel()
        self.name.setProperty("muted", True)
        self.count = QLabel()
        self.count.setFont(theme.mono(self.font()))
        lay.addWidget(self.dot)
        lay.addWidget(self.name, 1)
        lay.addWidget(self.count)

    def set(self, name: str, color: str, count: int) -> None:
        self.dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
        self.name.setText(name)
        self.count.setText(str(count))


class WeekBars(QWidget):
    """Sati po danu ove nedelje: stubići od ponedeljka do nedelje, današnji dan istaknut."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.days: list[tuple[date, float]] = []
        self.today = date.today()
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, days: list[tuple[date, float]], today: date) -> None:
        self.days, self.today = days, today
        self.update()

    def paintEvent(self, _e) -> None:
        if not self.days:
            return
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        peak = max((h for _, h in self.days), default=0) or 1
        n = len(self.days)
        label_h, value_h = 20, 18
        chart_h = self.height() - label_h - value_h - 4
        slot = self.width() / n
        bar_w = min(26.0, slot * 0.5)
        small = QFont(self.font())
        small.setPointSizeF(small.pointSizeF() - 1)
        p.setFont(small)
        for i, (d, hours) in enumerate(self.days):
            cx = slot * i + slot / 2
            is_today = d == self.today
            track = QRectF(cx - bar_w / 2, value_h, bar_w, chart_h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.surface_alt))
            p.drawRoundedRect(track, 6, 6)
            if hours > 0:
                h = max(8.0, chart_h * hours / peak)
                bar = QRectF(track.left(), track.bottom() - h, bar_w, h)
                color = QColor(t.accent)
                if not is_today:
                    color.setAlpha(150)
                p.setBrush(color)
                p.drawRoundedRect(bar, 6, 6)
                p.setPen(QColor(t.text if is_today else t.muted))
                p.drawText(
                    QRectF(cx - 30, bar.top() - value_h, 60, value_h),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{hours:g} h".replace(".", ","),
                )
            p.setPen(QColor(t.text if is_today else t.faint))
            f = QFont(small)
            f.setWeight(QFont.Weight.DemiBold if is_today else QFont.Weight.Normal)
            p.setFont(f)
            p.drawText(
                QRectF(cx - 20, self.height() - label_h, 40, label_h),
                Qt.AlignmentFlag.AlignCenter,
                WEEKDAYS_SHORT[d.weekday()],
            )
            p.setFont(small)


class FeedRow(QWidget):
    """Red u listi (rokovi, aktivnost): levi znak, dva reda teksta i desni dodatak."""

    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 5, 0, 5)
        self.lay.setSpacing(12)
        self.text = QVBoxLayout()
        self.text.setSpacing(1)
        self.title = QLabel()
        self.sub = QLabel()
        self.sub.setProperty("muted", True)
        f = self.sub.font()
        f.setPointSizeF(f.pointSizeF() - 0.75)
        self.sub.setFont(f)
        self.text.addWidget(self.title)
        self.text.addWidget(self.sub)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            QTimer.singleShot(0, self.clicked.emit)
        super().mouseReleaseEvent(event)


class DateBadge(QLabel):
    def __init__(self, d: date, tone: str, parent=None) -> None:
        super().__init__(parent)
        t = theme.tokens()
        bg = {"danger": t.danger_soft, "warning": t.warning_soft}.get(tone, t.surface_alt)
        fg = {"danger": t.danger, "warning": t.warning}.get(tone, t.text)
        self.setFixedSize(44, 44)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setStyleSheet(f"background: {bg}; border-radius: 10px; color: {fg};")
        self.setText(
            f"<div style='line-height:100%'><b style='font-size:15px'>{d.day}</b><br>"
            f"<span style='font-size:10px'>{MONTHS_SHORT[d.month - 1]}</span></div>"
        )


class FeedList(QWidget):
    """Vertikalna lista FeedRow redova sa tankom linijom između."""

    def __init__(self, empty_text: str, parent=None) -> None:
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)
        self.empty_text = empty_text

    def clear(self) -> None:
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add(self, row: QWidget) -> None:
        if self.lay.count():
            line = QFrame()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {theme.tokens().border};")
            self.lay.addWidget(line)
        self.lay.addWidget(row)

    def finish(self) -> None:
        if not self.lay.count():
            label = QLabel(self.empty_text)
            label.setProperty("faint", True)
            label.setWordWrap(True)
            self.lay.addWidget(label)
        self.lay.addStretch(1)


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
        body.setObjectName("ScrollBody")
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(22, 22, 22, 18)
        root.setSpacing(6)

        head = QVBoxLayout()
        head.setContentsMargins(8, 0, 8, 6)
        head.setSpacing(2)
        self.title = QLabel("Pregled")
        self.title.setObjectName("ProjectTitle")
        self.date_label = QLabel()
        self.date_label.setObjectName("PageSubtitle")
        head.addWidget(self.title)
        head.addWidget(self.date_label)
        root.addLayout(head)

        stats = QHBoxLayout()
        stats.setSpacing(4)
        self.s_projects = KpiCard("Aktivni projekti", "briefcase")
        self.s_open = KpiCard("Otvoreni zadaci", "tasks")
        self.s_late = KpiCard("Kasni", "warning", "danger")
        self.s_hours = KpiCard("Sati ove nedelje", "timer", "success")
        for s in (self.s_projects, self.s_open, self.s_late, self.s_hours):
            stats.addWidget(s, 1)
        root.addLayout(stats)

        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        for c in range(3):
            grid.setColumnStretch(c, 1)

        projects_card = Card("Projekti", icon="folder")
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
        for col, w in ((1, 130), (2, 110), (3, 56), (4, 180), (5, 82)):
            ph.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.projects.setColumnWidth(col, w)
        self.projects.itemClicked.connect(self._open_project)
        self.projects.setCursor(Qt.CursorShape.PointingHandCursor)
        self.projects.setMinimumHeight(150)
        projects_card.body.addWidget(self.projects)
        grid.addWidget(projects_card, 0, 0, 1, 2)

        ring_card = Card("Stanje zadataka", icon="chart")
        ring_row = QHBoxLayout()
        ring_row.setSpacing(18)
        self.ring = ProgressRing()
        ring_row.addWidget(self.ring)
        legend = QVBoxLayout()
        legend.setSpacing(8)
        legend.addStretch(1)
        self.legend: dict[TaskStatus, LegendRow] = {}
        for status in (TaskStatus.DONE, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.TODO):
            row = LegendRow()
            self.legend[status] = row
            legend.addWidget(row)
        legend.addStretch(1)
        ring_row.addLayout(legend, 1)
        ring_card.body.addLayout(ring_row)
        self.ring_note = QLabel()
        self.ring_note.setProperty("muted", True)
        ring_card.body.addWidget(self.ring_note)
        grid.addWidget(ring_card, 0, 2)

        deadlines_card = Card("Rokovi u narednih 14 dana", icon="calendar")
        self.deadlines = FeedList("Nema rokova u narednih 14 dana.")
        deadlines_card.body.addWidget(self.deadlines, 1)
        grid.addWidget(deadlines_card, 1, 0)

        activity_card = Card("Poslednje izmene", icon="pulse")
        self.activity = FeedList("Izmene zadataka pojaviće se ovde.")
        activity_card.body.addWidget(self.activity, 1)
        grid.addWidget(activity_card, 1, 1)

        hours_card = Card("Sati ove nedelje", icon="clock")
        self.week = WeekBars()
        hours_card.body.addWidget(self.week, 1)
        self.week_total = QLabel()
        self.week_total.setProperty("muted", True)
        hours_card.add_head_widget(self.week_total)
        grid.addWidget(hours_card, 1, 2)
        grid.setRowStretch(1, 1)
        root.addLayout(grid, 1)

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
        self.title.setText(greeting())
        self.date_label.setText(
            f"{long_date(ov.today).capitalize()}. Evo stanja svih aktivnih projekata."
        )
        done = ov.status_counts.get(TaskStatus.DONE, 0)
        self.s_projects.set(
            str(len(ov.projects)), f"{sum(1 for c in ov.projects if c.overdue)} sa kašnjenjem"
        )
        self.s_open.set(str(ov.open_tasks), f"{done} od {ov.total_tasks} završeno")
        self.s_late.set(
            str(ov.overdue_tasks),
            "rok je prošao" if ov.overdue_tasks else "sve je na vreme",
            t.danger if ov.overdue_tasks else None,
        )
        self.s_late.chip.set_tone("danger" if ov.overdue_tasks else "success")
        hours = ov.hours_this_week
        self.s_hours.set(format_hours(hours) if hours else "0 h", "od ponedeljka")

        self._fill_projects(ov)
        self.ring.set_data(ov.status_counts, ov.done_percent)
        colors = status_colors()
        for status, row in self.legend.items():
            row.set(TASK_STATUS[status], colors[status], ov.status_counts.get(status, 0))
        self.ring_note.setText(f"Ukupno {ov.total_tasks} zadataka u aktivnim projektima.")

        self.deadlines.clear()
        for d in ov.deadlines[:5]:
            row = FeedRow()
            tone = "danger" if d.overdue else ("warning" if d.days <= 1 else "")
            row.lay.addWidget(DateBadge(d.due, tone))
            row.title.setText(d.title)
            row.sub.setText(d.project_name)
            row.lay.addLayout(row.text, 1)
            when = QLabel(dashboard.relative_day(d.days))
            when.setObjectName("Pill")
            fg = {"danger": t.danger, "warning": t.warning}.get(tone, t.muted)
            bg = {"danger": t.danger_soft, "warning": t.warning_soft}.get(tone, t.surface_alt)
            when.setStyleSheet(f"color: {fg}; background: {bg};")
            row.lay.addWidget(when, 0, Qt.AlignmentFlag.AlignVCenter)
            row.clicked.connect(lambda d=d: self._go(d.project_id, d.task_id))
            self.deadlines.add(row)
        self.deadlines.finish()

        self.activity.clear()
        for a in ov.activity[:5]:
            row = FeedRow()
            name, tone = {
                "done": ("check-circle", "success"),
                "create": ("plus", "accent"),
                "delete": ("trash", "danger"),
            }.get(a.kind, ("pulse", "accent"))
            row.lay.addWidget(IconChip(name, tone, 32), 0, Qt.AlignmentFlag.AlignTop)
            row.title.setText(a.text)
            row.title.setWordWrap(True)
            row.sub.setText(f"{a.project_name}, {dashboard.time_ago(a.when)}")
            row.lay.addLayout(row.text, 1)
            row.clicked.connect(lambda a=a: self._go(a.project_id, ""))
            self.activity.add(row)
        self.activity.finish()

        self.week.set_data(ov.week_days, ov.today)
        self.week_total.setText(format_hours(hours) if hours else "")

    def _fill_projects(self, ov) -> None:
        t = theme.tokens()
        self.projects.clear()
        mono = theme.mono(self.projects.font(), -0.5)
        for c in ov.projects:
            item = QTreeWidgetItem([c.name, "", "", "", "", ""])
            item.setIcon(0, color_dot(c.color))
            item.setData(0, ROLE_ID, c.id)
            item.setToolTip(0, c.name + (f"\n{c.client}" if c.client else ""))
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

    def _go(self, pid: str, tid: str) -> None:
        if not pid:
            return
        self.ctx.open_project(pid)
        if tid:
            self.ctx.open_task_requested.emit(tid)

    def _open_project(self, item: QTreeWidgetItem) -> None:
        pid = item.data(0, ROLE_ID)
        if pid:
            QTimer.singleShot(0, lambda: self.ctx.open_project(pid))

    def _open_deadline(self, item: QTreeWidgetItem) -> None:
        pid, tid = item.data(0, ROLE_ID), item.data(0, ROLE_TASK)
        if pid:
            QTimer.singleShot(0, lambda: self._go(pid, tid))
