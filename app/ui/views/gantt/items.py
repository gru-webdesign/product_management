"""Elementi Gant grafikona: traka zadatka, milestone i strelica zavisnosti.

Traka se pomera i razvlači mišem; nove vrednosti se ne pišu u bazu dok se miš ne pusti.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsPathItem

from app.db.models import DependencyType, TaskStatus
from app.services.gantt_math import describe_span
from app.ui import theme
from app.ui.views.gantt.model import BAR_H, HANDLE_R, ROW_H, DepData, MilestoneData, RowData

if TYPE_CHECKING:
    from app.ui.views.gantt.chart import GanttChart

EDGE = 7  # piksela od ivice trake u kojima se menja trajanje


class TaskBarItem(QGraphicsObject):
    def __init__(self, chart: GanttChart, row: RowData, index: int) -> None:
        super().__init__()
        self.chart = chart
        self.row = row
        self.index = index
        self.start: date = row.start
        self.end: date = row.end
        self._mode = ""
        self._press_x = 0.0
        self._orig = (row.start, row.end)
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(10)
        self.setToolTip(
            f"{row.title}\n{describe_span(row.start, row.end)}\n{row.progress}% urađeno"
        )

    # --- geometrija ------------------------------------------------------------------------------

    def bar_rect(self) -> QRectF:
        x0 = self.chart.x_of(self.start)
        x1 = self.chart.x_end_of(self.end)
        h = BAR_H - 6 if self.row.has_children else BAR_H
        y = self.chart.row_y(self.index) + (ROW_H - h) / 2
        return QRectF(x0, y, max(x1 - x0, 4.0), h)

    def handle_center(self) -> QPointF:
        r = self.bar_rect()
        return QPointF(r.right() + HANDLE_R + 4, r.center().y())

    def boundingRect(self) -> QRectF:
        r = self.bar_rect()
        label_w = QFontMetricsF(self._label_font()).horizontalAdvance(self.row.title) + 16
        return r.adjusted(-2, -6, label_w + 2 * HANDLE_R + 10, 6)

    def _label_font(self) -> QFont:
        f = QFont(self.chart.font())
        f.setPointSizeF(max(7.5, f.pointSizeF() - 0.75))
        return f

    # --- crtanje ---------------------------------------------------------------------------------

    def colors(self) -> tuple[QColor, QColor]:
        t = theme.tokens()
        if self.row.done:
            base = QColor(t.success)
        elif self.row.overdue:
            base = QColor(t.danger)
        elif self.row.status == TaskStatus.REVIEW:
            base = QColor(t.warning)
        else:
            base = QColor(t.accent)
        soft = QColor(base)
        soft.setAlpha(70 if t.name == "light" else 95)
        return base, soft

    def paint(self, p: QPainter, _option, _widget=None) -> None:
        t = theme.tokens()
        r = self.bar_rect()
        base, soft = self.colors()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 3 if self.row.has_children else 5
        selected = self.isSelected() or self.chart.selected_task == self.row.task_id
        if self.row.has_children:
            # zbirni (roditeljski) zadatak: tamna tanka traka sa „nožicama"
            dark = QColor(t.text)
            dark.setAlpha(200)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dark)
            p.drawRoundedRect(r, radius, radius)
            for x in (r.left(), r.right() - 5):
                path = QPainterPath()
                path.moveTo(x, r.bottom())
                path.lineTo(x + 5, r.bottom())
                path.lineTo(x + (0 if x == r.left() else 5), r.bottom() + 5)
                path.closeSubpath()
                p.drawPath(path)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(soft)
            p.drawRoundedRect(r, radius, radius)
            pct = 100 if self.row.done else self.row.progress
            if pct > 0:
                p.save()
                clip = QPainterPath()
                clip.addRoundedRect(r, radius, radius)
                p.setClipPath(clip)
                p.setBrush(base)
                p.drawRect(QRectF(r.left(), r.top(), r.width() * pct / 100, r.height()))
                p.restore()
            if r.width() > 38 and 0 < pct < 100:
                f = self._label_font()
                f.setWeight(QFont.Weight.DemiBold)
                p.setFont(f)
                p.setPen(QColor("#FFFFFF") if pct > 40 else QColor(t.text))
                p.drawText(
                    r.adjusted(6, 0, -4, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    f"{pct}%",
                )
        if selected or self._mode:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.text), 1.5))
            p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 1, radius + 1)

        # naziv desno od trake
        p.setFont(self._label_font())
        p.setPen(QColor(t.faint if self.row.done else t.muted))
        label_x = r.right() + (2 * HANDLE_R + 14 if self._hover else 14)
        p.drawText(
            QRectF(label_x, r.top() - 4, 600, r.height() + 8),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.row.title,
        )

        if self._hover and not self._mode:
            c = self.handle_center()
            p.setPen(QPen(QColor(t.accent), 1.5))
            p.setBrush(QColor(t.surface))
            p.drawEllipse(c, HANDLE_R, HANDLE_R)

    # --- miš -------------------------------------------------------------------------------------

    def _zone(self, pos: QPointF) -> str:
        r = self.bar_rect()
        c = self.handle_center()
        if (pos - c).manhattanLength() <= HANDLE_R + 3:
            return "link"
        if not r.adjusted(-2, -3, 2, 3).contains(pos):
            return ""
        if r.width() >= 3 * EDGE:
            if pos.x() <= r.left() + EDGE:
                return "start"
            if pos.x() >= r.right() - EDGE:
                return "end"
        return "move"

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self.bar_rect().adjusted(-2, -3, 2, 3), 5, 5)
        if self._hover:
            path.addEllipse(self.handle_center(), HANDLE_R + 3, HANDLE_R + 3)
        return path

    def hoverEnterEvent(self, event) -> None:
        self.prepareGeometryChange()
        self._hover = True
        self.update()

    def hoverMoveEvent(self, event) -> None:
        zone = self._zone(event.pos())
        cursor = {
            "start": Qt.CursorShape.SizeHorCursor,
            "end": Qt.CursorShape.SizeHorCursor,
            "move": Qt.CursorShape.OpenHandCursor,
            "link": Qt.CursorShape.CrossCursor,
        }.get(zone, Qt.CursorShape.ArrowCursor)
        self.setCursor(cursor)

    def hoverLeaveEvent(self, event) -> None:
        self.prepareGeometryChange()
        self._hover = False
        self.unsetCursor()
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._mode = self._zone(event.pos()) or "move"
        self._press_x = event.scenePos().x()
        self._orig = (self.start, self.end)
        self.chart.select_task(self.row.task_id)
        if self._mode == "move":
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        if self._mode == "link":
            self.chart.begin_link(self, event.scenePos())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._mode:
            return
        if self._mode == "link":
            self.chart.update_link(event.scenePos())
            return
        days = self.chart.scale.days_for(event.scenePos().x() - self._press_x)
        s0, e0 = self._orig
        delta = timedelta(days=days)
        if self._mode == "move":
            start, end = s0 + delta, e0 + delta
        elif self._mode == "start":
            start, end = min(s0 + delta, e0), e0
        else:
            start, end = s0, max(e0 + delta, s0)
        if (start, end) != (self.start, self.end):
            self.prepareGeometryChange()
            self.start, self.end = start, end
            self.update()
            self.chart.refresh_dependencies()
        self.chart.show_hint(describe_span(self.start, self.end), event.scenePos())

    def mouseReleaseEvent(self, event) -> None:
        mode, self._mode = self._mode, ""
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.chart.show_hint("", None)
        if mode == "link":
            self.chart.end_link(event.scenePos())
            return
        if (self.start, self.end) != self._orig:
            self.chart.dates_committed.emit(self.row.task_id, self.start, self.end)
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        self.chart.open_task.emit(self.row.task_id)

    def contextMenuEvent(self, event) -> None:
        self.chart.select_task(self.row.task_id)
        self.chart.task_menu.emit(self.row.task_id, event.screenPos())


class MilestoneItem(QGraphicsObject):
    SIZE = 9

    def __init__(self, chart: GanttChart, m: MilestoneData, index: int) -> None:
        super().__init__()
        self.chart = chart
        self.m = m
        self.index = index
        self.day = m.date
        self._press_x = 0.0
        self._orig = m.date
        self._dragging = False
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(12)
        self.setToolTip(
            f"{m.name}\n{m.date.strftime('%d.%m.%Y.')}" + ("\nostvaren" if m.done else "")
        )

    def center(self) -> QPointF:
        x = self.chart.x_of(self.day) + self.chart.scale.px_per_day / 2
        return QPointF(x, self.chart.row_y(self.index) + ROW_H / 2)

    def boundingRect(self) -> QRectF:
        c = self.center()
        f = QFont(self.chart.font())
        w = QFontMetricsF(f).horizontalAdvance(self.m.name) + 20
        return QRectF(
            c.x() - self.SIZE - 2, c.y() - self.SIZE - 2, 2 * self.SIZE + w + 4, 2 * self.SIZE + 4
        )

    def shape(self) -> QPainterPath:
        c = self.center()
        path = QPainterPath()
        path.addRect(
            QRectF(
                c.x() - self.SIZE - 2, c.y() - self.SIZE - 2, 2 * self.SIZE + 4, 2 * self.SIZE + 4
            )
        )
        return path

    def paint(self, p: QPainter, _o, _w=None) -> None:
        t = theme.tokens()
        c = self.center()
        s = self.SIZE
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.moveTo(c.x(), c.y() - s)
        path.lineTo(c.x() + s, c.y())
        path.lineTo(c.x(), c.y() + s)
        path.lineTo(c.x() - s, c.y())
        path.closeSubpath()
        color = QColor(t.success if self.m.done else t.text)
        p.setPen(QPen(QColor(t.surface), 1.5))
        p.setBrush(color)
        p.drawPath(path)
        p.setPen(QColor(t.text))
        f = QFont(self.chart.font())
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.drawText(
            QRectF(c.x() + s + 6, c.y() - 10, 400, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.m.name,
        )

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._press_x = event.scenePos().x()
        self._orig = self.day
        self._dragging = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        days = self.chart.scale.days_for(event.scenePos().x() - self._press_x)
        new = self._orig + timedelta(days=days)
        if new != self.day:
            self.prepareGeometryChange()
            self.day = new
            self.update()
        self.chart.show_hint(self.day.strftime("%d.%m.%Y."), event.scenePos())

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.chart.show_hint("", None)
        if self.day != self._orig:
            self.chart.milestone_moved.emit(self.m.id, self.day)

    def mouseDoubleClickEvent(self, event) -> None:
        self.chart.open_milestone.emit(self.m.id)


class DependencyItem(QGraphicsPathItem):
    def __init__(self, chart: GanttChart, dep: DepData) -> None:
        super().__init__()
        self.chart = chart
        self.dep = dep
        self._hover = False
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(5)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rebuild()

    def rebuild(self) -> None:
        pred = self.chart.bars.get(self.dep.predecessor_id)
        succ = self.chart.bars.get(self.dep.successor_id)
        if not pred or not succ:
            self.setPath(QPainterPath())
            return
        a, b = pred.bar_rect(), succ.bar_rect()
        y1, y2 = a.center().y(), b.center().y()
        gap = 8
        path = QPainterPath()
        if self.dep.type == DependencyType.START_TO_START:
            x1, x2 = a.left(), b.left()
            xm = min(x1, x2) - gap
            path.moveTo(x1, y1)
            path.lineTo(xm, y1)
            path.lineTo(xm, y2)
            path.lineTo(x2, y2)
            self._arrow_end = (QPointF(x2, y2), 1)
        elif self.dep.type == DependencyType.FINISH_TO_FINISH:
            x1, x2 = a.right(), b.right()
            xm = max(x1, x2) + gap
            path.moveTo(x1, y1)
            path.lineTo(xm, y1)
            path.lineTo(xm, y2)
            path.lineTo(x2, y2)
            self._arrow_end = (QPointF(x2, y2), -1)
        else:  # FS
            x1, x2 = a.right(), b.left()
            path.moveTo(x1, y1)
            if x2 - gap >= x1 + gap:
                path.lineTo(x1 + gap, y1)
                path.lineTo(x1 + gap, y2)
                path.lineTo(x2, y2)
            else:
                mid = y1 + (ROW_H / 2 if y2 > y1 else -ROW_H / 2)
                path.lineTo(x1 + gap, y1)
                path.lineTo(x1 + gap, mid)
                path.lineTo(x2 - gap, mid)
                path.lineTo(x2 - gap, y2)
                path.lineTo(x2, y2)
            self._arrow_end = (QPointF(x2, y2), 1)
        tip, direction = self._arrow_end
        path.moveTo(tip)
        path.lineTo(tip.x() - 6 * direction, tip.y() - 4)
        path.moveTo(tip)
        path.lineTo(tip.x() - 6 * direction, tip.y() + 4)
        self.prepareGeometryChange()
        self.setPath(path)

    def shape(self) -> QPainterPath:
        from PySide6.QtGui import QPainterPathStroker

        stroker = QPainterPathStroker()
        stroker.setWidth(9)
        return stroker.createStroke(self.path())

    def paint(self, p: QPainter, _o, _w=None) -> None:
        t = theme.tokens()
        active = self._hover or self.isSelected()
        color = QColor(t.accent if active else t.faint)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(
            QPen(
                color,
                2 if active else 1.3,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        p.drawPath(self.path())

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def contextMenuEvent(self, event) -> None:
        self.setSelected(True)
        self.chart.dependency_menu.emit(self.dep.id, event.screenPos())

    def mouseDoubleClickEvent(self, event) -> None:
        self.chart.open_task.emit(self.dep.successor_id)
