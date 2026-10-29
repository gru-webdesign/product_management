"""Gant grafikon kao jedan QGraphicsView.

Leva kolona sa nazivima i zaglavlje sa datumima crtaju se preko scene (drawForeground) i ostaju
na mestu pri skrolovanju, pa su redovi uvek poravnati sa trakama. Scena počinje desno od leve
kolone (x = left_w) i ispod zaglavlja (y = HEADER_H).
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView

from app.labels import TASK_STATUS_COLOR
from app.services.gantt_math import TimeScale, header_ticks, is_weekend, make_scale
from app.services.money import format_money
from app.ui import theme
from app.ui.views.gantt.items import DependencyItem, MilestoneItem, TaskBarItem
from app.ui.views.gantt.model import (
    COST_W,
    HEADER_H,
    LEFT_W,
    ROW_H,
    DepData,
    MilestoneData,
    RowData,
)

MILESTONE_ROW = 0


class GanttChart(QGraphicsView):
    dates_committed = Signal(str, object, object)  # task_id, početak, kraj
    milestone_moved = Signal(str, object)
    link_requested = Signal(str, str)  # prethodnik, naslednik
    open_task = Signal(str)
    open_milestone = Signal(str)
    schedule_undated = Signal(str, object)  # zadatak bez datuma, kliknuti dan
    task_menu = Signal(str, QPoint)
    dependency_menu = Signal(str, QPoint)
    zoom_step = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

        self.rows: list[RowData] = []
        self.milestones: list[MilestoneData] = []
        self.deps: list[DepData] = []
        self.bars: dict[str, TaskBarItem] = {}
        self.dep_items: list[DependencyItem] = []
        self.zoom = "day"
        self.show_cost = False
        self.scale = TimeScale(date.today(), 60, 38.0)
        self.today = date.today()
        self.selected_task = ""
        self._hover_row = -1
        self._hint = ("", None)
        self._link_from: TaskBarItem | None = None
        self._link_to: QPointF | None = None

    # --- koordinate ------------------------------------------------------------------------------

    @property
    def left_w(self) -> int:
        return LEFT_W + (COST_W if self.show_cost else 0)

    def x_of(self, d: date) -> float:
        return self.left_w + self.scale.x(d)

    def x_end_of(self, d: date) -> float:
        return self.left_w + self.scale.x_end(d)

    def row_y(self, index: int) -> float:
        """Gornja ivica reda u sceni. Red 0 su milestone-i, zadaci kreću od 1."""
        return HEADER_H + index * ROW_H

    def row_at(self, scene_y: float) -> int:
        if scene_y < HEADER_H:
            return -1
        i = int((scene_y - HEADER_H) // ROW_H)
        return i if 0 <= i <= len(self.rows) else -1

    def task_at_row(self, i: int) -> RowData | None:
        return self.rows[i - 1] if 1 <= i <= len(self.rows) else None

    # --- podaci ----------------------------------------------------------------------------------

    def set_data(
        self,
        rows: list[RowData],
        milestones: list[MilestoneData],
        deps: list[DepData],
        zoom: str,
        show_cost: bool,
        extra_dates: list[date] | None = None,
    ) -> None:
        h = self.horizontalScrollBar().value()
        v = self.verticalScrollBar().value()
        first = not self.rows and not self.bars
        zoom_changed = zoom != self.zoom
        old_center_date = self._center_date() if zoom_changed else None

        self.rows, self.milestones, self.deps = rows, milestones, deps
        self.zoom, self.show_cost = zoom, show_cost
        self.today = date.today()
        dates = [d for r in rows for d in (r.start, r.end)] + [m.date for m in milestones]
        self.scale = make_scale(dates + (extra_dates or []), self.today, zoom)

        scene = self.scene()
        scene.clear()
        self.bars.clear()
        self.dep_items.clear()
        height = HEADER_H + (len(rows) + 1) * ROW_H + ROW_H * 2
        scene.setSceneRect(QRectF(0, 0, self.left_w + self.scale.width + 120, height))

        for i, m in enumerate(milestones):
            scene.addItem(MilestoneItem(self, m, MILESTONE_ROW))
            del i
        for i, row in enumerate(rows, start=1):
            if row.dated:
                bar = TaskBarItem(self, row, i)
                scene.addItem(bar)
                self.bars[row.task_id] = bar
        for dep in deps:
            item = DependencyItem(self, dep)
            scene.addItem(item)
            self.dep_items.append(item)

        if first:
            self.scroll_to(self.today - timedelta(days=3))
        elif old_center_date:
            self.scroll_to(old_center_date, center=True)
            self.verticalScrollBar().setValue(v)
        else:
            self.horizontalScrollBar().setValue(h)
            self.verticalScrollBar().setValue(v)
        self.viewport().update()

    def refresh_dependencies(self) -> None:
        for item in self.dep_items:
            item.rebuild()

    def select_task(self, task_id: str) -> None:
        self.selected_task = task_id
        for bar in self.bars.values():
            bar.update()
        self.viewport().update()

    # --- skrol i zum -----------------------------------------------------------------------------

    def _center_date(self) -> date:
        x = self.horizontalScrollBar().value() + (self.viewport().width() + self.left_w) / 2
        return self.scale.date_at(x - self.left_w)

    def scroll_to(self, d: date, center: bool = False) -> None:
        x = self.scale.x(d)
        if center:
            x -= (self.viewport().width() - self.left_w) / 2
        self.horizontalScrollBar().setValue(int(max(0, x)))

    def wheelEvent(self, event) -> None:
        mods = event.modifiers()
        dy = event.angleDelta().y()
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.zoom_step.emit(1 if dy > 0 else -1)
            event.accept()
            return
        if mods & Qt.KeyboardModifier.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - dy)
            event.accept()
            return
        super().wheelEvent(event)

    # --- povezivanje mišem -----------------------------------------------------------------------

    def begin_link(self, bar: TaskBarItem, pos: QPointF) -> None:
        self._link_from = bar
        self._link_to = pos
        self.viewport().update()

    def update_link(self, pos: QPointF) -> None:
        self._link_to = pos
        target = self._bar_at(pos)
        name = target.row.title if target and target is not self._link_from else ""
        self.show_hint(
            f"Poveži: „{self._link_from.row.title}“ → „{name}“"
            if name
            else "Pusti na traku zadatka koji čeka na ovaj",
            pos,
        )
        self.viewport().update()

    def end_link(self, pos: QPointF) -> None:
        source, self._link_from, self._link_to = self._link_from, None, None
        target = self._bar_at(pos)
        self.viewport().update()
        if source and target and target is not source:
            self.link_requested.emit(source.row.task_id, target.row.task_id)

    def _bar_at(self, pos: QPointF) -> TaskBarItem | None:
        for item in self.scene().items(pos):
            if isinstance(item, TaskBarItem) and item.bar_rect().adjusted(-4, -6, 4, 6).contains(
                pos
            ):
                return item
        i = self.row_at(pos.y())
        row = self.task_at_row(i)
        return self.bars.get(row.task_id) if row else None

    def show_hint(self, text: str, pos: QPointF | None) -> None:
        self._hint = (text, pos)
        self.viewport().update()

    # --- miš na zamrznutim delovima --------------------------------------------------------------

    def _in_frozen(self, p: QPoint) -> bool:
        return p.x() < self.left_w or p.y() < HEADER_H

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._in_frozen(pos):
            if pos.y() >= HEADER_H:
                row = self.task_at_row(self.row_at(self.mapToScene(pos).y()))
                if row:
                    self.select_task(row.task_id)
                    if event.button() == Qt.MouseButton.RightButton:
                        self.task_menu.emit(row.task_id, event.globalPosition().toPoint())
            event.accept()
            return
        if not self.itemAt(pos):
            self.scene().clearSelection()
            row = self.task_at_row(self.row_at(self.mapToScene(pos).y()))
            self.select_task(row.task_id if row else "")
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        pos = event.position().toPoint()
        scene_pos = self.mapToScene(pos)
        i = self.row_at(scene_pos.y())
        if i == MILESTONE_ROW and pos.x() < self.left_w:
            return
        row = self.task_at_row(i)
        if self._in_frozen(pos):
            if row:
                self.open_task.emit(row.task_id)
            return
        if row and not row.dated and not self.itemAt(pos):
            self.schedule_undated.emit(row.task_id, self.scale.date_at(scene_pos.x() - self.left_w))
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        i = self.row_at(self.mapToScene(event.position().toPoint()).y())
        if i != self._hover_row:
            self._hover_row = i
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_row = -1
        self.viewport().update()
        super().leaveEvent(event)

    def contextMenuEvent(self, event) -> None:
        if self._in_frozen(event.pos()):
            event.accept()
            return
        super().contextMenuEvent(event)

    # --- crtanje ---------------------------------------------------------------------------------

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:
        t = theme.tokens()
        p.fillRect(rect, QColor(t.surface))
        ppd = self.scale.px_per_day
        left, right = max(rect.left(), self.left_w), rect.right()
        top, bottom = rect.top(), rect.bottom()
        rows_bottom = self.row_y(len(self.rows) + 1)

        # vikendi
        if self.zoom in ("day", "week"):
            first = self.scale.date_at(left - self.left_w)
            last = self.scale.date_at(right - self.left_w)
            d = first
            while d <= last:
                if is_weekend(d):
                    p.fillRect(QRectF(self.x_of(d), top, ppd, bottom - top), QColor(t.weekend))
                d += timedelta(days=1)

        # izabrani i red pod mišem
        for idx, alpha in ((self._selected_index(), 255), (self._hover_row, 120)):
            if idx >= 1:
                c = QColor(t.accent_soft)
                c.setAlpha(alpha)
                p.fillRect(QRectF(left, self.row_y(idx), right - left, ROW_H), c)

        # vertikalne linije (početak nedelje / meseca)
        _top, ticks = header_ticks(self.scale, self.zoom)
        pen_light = QPen(QColor(t.grid), 1)
        pen_strong = QPen(QColor(t.border), 1)
        for tick in ticks:
            x = self.left_w + tick.x
            if left - 1 <= x <= right + 1:
                p.setPen(pen_strong if tick.strong else pen_light)
                p.drawLine(QPointF(x, top), QPointF(x, bottom))

        # horizontalne linije redova
        p.setPen(QPen(QColor(t.grid), 1))
        for i in range(len(self.rows) + 2):
            y = self.row_y(i)
            if top - 1 <= y <= bottom + 1:
                p.drawLine(QPointF(left, y), QPointF(right, y))
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(QPointF(left, self.row_y(1)), QPointF(right, self.row_y(1)))

        # kraj liste redova
        if rows_bottom < bottom:
            p.fillRect(
                QRectF(left, rows_bottom, right - left, bottom - rows_bottom), QColor(t.surface)
            )

        # danas
        if self.scale.contains(self.today):
            x = self.x_of(self.today) + ppd / 2
            pen = QPen(QColor(t.today), 1.5)
            p.setPen(pen)
            p.drawLine(QPointF(x, HEADER_H), QPointF(x, max(bottom, rows_bottom)))

    def _selected_index(self) -> int:
        for i, row in enumerate(self.rows, start=1):
            if row.task_id == self.selected_task:
                return i
        return -1

    def drawForeground(self, p: QPainter, rect: QRectF) -> None:
        # Crtanje u koordinatama prozora (preko scene), pa ostaje na mestu pri skrolovanju.
        if self._link_from and self._link_to is not None:
            t = theme.tokens()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor(t.accent), 1.6, Qt.PenStyle.DashLine))
            p.drawLine(self._link_from.handle_center(), self._link_to)
        p.save()
        p.resetTransform()
        self._paint_left(p)
        self._paint_header(p)
        self._paint_hint(p)
        p.restore()

    def _paint_header(self, p: QPainter) -> None:
        t = theme.tokens()
        w = self.viewport().width()
        hs = self.horizontalScrollBar().value()
        p.fillRect(QRectF(0, 0, w, HEADER_H), QColor(t.surface))
        top_ticks, bottom_ticks = header_ticks(self.scale, self.zoom)
        mid = HEADER_H / 2
        base = QFont(self.font())
        small = QFont(base)
        small.setPointSizeF(max(7.0, base.pointSizeF() - 1.25))
        strong = QFont(base)
        strong.setWeight(QFont.Weight.DemiBold)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        p.setFont(strong)
        for tick in top_ticks:
            x0 = self.left_w + tick.x - hs
            x1 = x0 + tick.width
            if x1 < self.left_w or x0 > w:
                continue
            p.setPen(QPen(QColor(t.border), 1))
            p.drawLine(QPointF(x0, 6), QPointF(x0, HEADER_H))
            label_x = max(x0, self.left_w) + 8
            p.setPen(QColor(t.text))
            p.drawText(
                QRectF(label_x, 4, max(0, x1 - label_x), mid - 4),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                tick.label,
            )

        p.setFont(small)
        fm = QFontMetricsF(small)
        today_label = None
        for tick in bottom_ticks:
            x0 = self.left_w + tick.x - hs
            if x0 + tick.width < self.left_w or x0 > w:
                continue
            label = tick.label
            if fm.horizontalAdvance(label) > tick.width - 4:
                label = label.split(" ")[-1]
            if fm.horizontalAdvance(label) > tick.width - 2:
                continue
            day = self.scale.date_at(tick.x)
            is_today = self.zoom == "day" and day == self.today
            weekend = self.zoom == "day" and is_weekend(day)
            p.setPen(QColor(t.today if is_today else (t.faint if weekend else t.muted)))
            r = QRectF(x0, mid, tick.width, mid - 4)
            align = (
                Qt.AlignmentFlag.AlignCenter
                if self.zoom == "day"
                else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            p.drawText(r.adjusted(0 if self.zoom == "day" else 6, 0, 0, 0), align, label)
            if is_today:
                today_label = r
        if today_label is None and self.scale.contains(self.today):
            x = self.left_w + self.scale.x(self.today) + self.scale.px_per_day / 2 - hs
            if x > self.left_w:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.today))
                p.drawEllipse(QPointF(x, HEADER_H - 4), 3, 3)
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(QPointF(0, HEADER_H - 0.5), QPointF(w, HEADER_H - 0.5))

    def _paint_left(self, p: QPainter) -> None:
        t = theme.tokens()
        vs = self.verticalScrollBar().value()
        h = self.viewport().height()
        lw = self.left_w
        p.fillRect(QRectF(0, 0, lw, h), QColor(t.surface))

        base = QFont(self.font())
        bold = QFont(base)
        bold.setWeight(QFont.Weight.Medium)
        small = QFont(base)
        small.setPointSizeF(max(7.0, base.pointSizeF() - 1))
        sel = self._selected_index()

        first = max(0, int((vs) // ROW_H) - 1)
        last = min(len(self.rows), int((vs + h) // ROW_H) + 1)
        for i in range(first, last + 1):
            y = self.row_y(i) - vs
            if y + ROW_H < HEADER_H or y > h:
                continue
            rect = QRectF(0, y, lw, ROW_H)
            if i == sel:
                p.fillRect(rect, QColor(t.accent_soft))
            elif i == self._hover_row and i >= 1:
                c = QColor(t.accent_soft)
                c.setAlpha(120)
                p.fillRect(rect, c)
            p.setPen(QPen(QColor(t.grid), 1))
            p.drawLine(QPointF(0, y + ROW_H), QPointF(lw, y + ROW_H))
            if i == MILESTONE_ROW:
                p.setFont(small)
                p.setPen(QColor(t.faint))
                n = len(self.milestones)
                label = f"MILESTONE-I  ·  {n}" if n else "MILESTONE-I"
                p.drawText(
                    QRectF(16, y, lw - 24, ROW_H),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    label,
                )
                continue
            row = self.rows[i - 1]
            indent = 16 + row.depth * 16
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(TASK_STATUS_COLOR[row.status]))
            p.drawEllipse(QPointF(indent + 3, y + ROW_H / 2), 3.5, 3.5)
            p.setFont(bold if row.depth == 0 else base)
            p.setPen(QColor(t.faint if row.done else t.text))
            text_w = LEFT_W - indent - 22
            fm = QFontMetricsF(p.font())
            title = fm.elidedText(row.title, Qt.TextElideMode.ElideRight, text_w)
            p.drawText(
                QRectF(indent + 14, y, text_w, ROW_H),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                title,
            )
            if not row.dated:
                p.setFont(small)
                p.setPen(QColor(t.faint))
                p.drawText(
                    QRectF(lw + 12, y, 260, ROW_H),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    "bez datuma — dupli klik u redu postavlja datum",
                )
            if self.show_cost:
                p.setFont(small)
                p.setPen(QColor(t.muted))
                p.drawText(
                    QRectF(LEFT_W, y, COST_W - 12, ROW_H),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    format_money(row.cost_minor) if row.cost_minor else "—",
                )

        # zaglavlje leve kolone
        p.fillRect(QRectF(0, 0, lw, HEADER_H), QColor(t.surface))
        p.setFont(small)
        p.setPen(QColor(t.muted))
        p.drawText(
            QRectF(16, 0, LEFT_W - 16, HEADER_H - 6),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            "ZADATAK",
        )
        if self.show_cost:
            p.drawText(
                QRectF(LEFT_W, 0, COST_W - 12, HEADER_H - 6),
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                "TROŠAK",
            )
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(QPointF(lw - 0.5, 0), QPointF(lw - 0.5, h))

    def _paint_hint(self, p: QPainter) -> None:
        text, pos = self._hint
        if not text or pos is None:
            return
        t = theme.tokens()
        vp = self.mapFromScene(pos)
        f = QFont(self.font())
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        fm = QFontMetricsF(f)
        w, h = fm.horizontalAdvance(text) + 20, fm.height() + 10
        x = min(max(vp.x() + 14, self.left_w + 4), self.viewport().width() - w - 4)
        y = max(vp.y() - h - 10, HEADER_H + 4)
        r = QRectF(x, y, w, h)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.text))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor(t.bg))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
