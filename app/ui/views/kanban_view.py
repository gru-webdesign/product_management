"""Prikaz Kanban: kolona po statusu, kartice se prevlače mišem između kolona."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
)

from app.db.models import TaskStatus
from app.labels import PRIORITY, PRIORITY_COLOR, TASK_STATUS, TASK_STATUS_COLOR
from app.services import tasks as task_service
from app.services.tasks import TaskFilter, is_overdue
from app.ui import icons, theme
from app.ui.dialogs.task_dialog import open_task
from app.ui.views.base import ProjectView
from app.ui.widgets.paint import draw_pill, draw_progress

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_CARD = Qt.ItemDataRole.UserRole + 1
PAD = 12
GAP = 8


class CardDelegate(QStyledItemDelegate):
    def _fonts(self, base: QFont) -> tuple[QFont, QFont]:
        title = QFont(base)
        title.setWeight(QFont.Weight.Medium)
        small = QFont(base)
        small.setPointSizeF(max(7.5, base.pointSizeF() - 1))
        return title, small

    def _title_rect(self, width: int, fm: QFontMetrics, text: str) -> QRect:
        r = fm.boundingRect(QRect(0, 0, width - 2 * PAD, 1000), int(Qt.TextFlag.TextWordWrap), text)
        return QRect(0, 0, width - 2 * PAD, min(r.height(), fm.lineSpacing() * 3))

    def sizeHint(self, option, index) -> QSize:
        card = index.data(ROLE_CARD) or {}
        width = max(160, option.widget.viewport().width() - 4) if option.widget else 240
        title_font, small = self._fonts(option.font)
        h = PAD
        if card.get("parent"):
            h += QFontMetrics(small).height() + 2
        h += self._title_rect(width, QFontMetrics(title_font), card.get("title", "")).height()
        h += 8 + 22  # meta red
        if card.get("progress"):
            h += 12
        if card.get("tags"):
            h += QFontMetrics(small).height() + 4
        return QSize(width, h + PAD + GAP)

    def paint(self, p: QPainter, option, index) -> None:
        card = index.data(ROLE_CARD) or {}
        t = theme.tokens()
        title_font, small = self._fonts(option.font)
        rect = option.rect.adjusted(2, 0, -2, -GAP)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = option.state & QStyle.StateFlag.State_Selected
        hover = option.state & QStyle.StateFlag.State_MouseOver
        border = QColor(t.accent if selected else (t.border_strong if hover else t.border))
        p.setPen(QPen(border, 1.5 if selected else 1))
        p.setBrush(QColor(t.surface))
        p.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        # traka prioriteta levo
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PRIORITY_COLOR[card["priority"]]))
        p.drawRoundedRect(QRectF(rect.left() + 1, rect.top() + 10, 3, rect.height() - 20), 1.5, 1.5)

        x, y, w = rect.left() + PAD, rect.top() + PAD, rect.width() - 2 * PAD
        if card.get("parent"):
            p.setFont(small)
            p.setPen(QColor(t.faint))
            fm = QFontMetrics(small)
            p.drawText(
                QRect(x, y, w, fm.height()),
                Qt.AlignmentFlag.AlignLeft,
                fm.elidedText(f"↳ {card['parent']}", Qt.TextElideMode.ElideRight, w),
            )
            y += fm.height() + 2
        p.setFont(title_font)
        p.setPen(QColor(t.faint if card["done"] else t.text))
        tr = self._title_rect(rect.width(), QFontMetrics(title_font), card["title"])
        p.drawText(QRect(x, y, w, tr.height()), int(Qt.TextFlag.TextWordWrap), card["title"])
        y += tr.height() + 8

        meta = QRect(x, y, w, 22)
        used = draw_pill(
            p, meta, PRIORITY[card["priority"]], PRIORITY_COLOR[card["priority"]], small
        )
        if card.get("due"):
            p.setFont(small)
            p.setPen(QColor(t.danger if card["overdue"] else t.muted))
            p.drawText(
                meta.adjusted(used + 10, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                ("Kasni · " if card["overdue"] else "Rok ") + card["due"],
            )
        if card.get("estimate"):
            p.setFont(small)
            p.setPen(QColor(t.faint))
            p.drawText(
                meta,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                f"{card['estimate']:g} h",
            )
        y += 22
        if card.get("progress"):
            draw_progress(p, QRect(x, y + 2, w, 10), card["progress"], label=False)
            y += 12
        if card.get("tags"):
            p.setFont(small)
            p.setPen(QColor(t.muted))
            fm = QFontMetrics(small)
            p.drawText(
                QRect(x, y + 4, w, fm.height()),
                Qt.AlignmentFlag.AlignLeft,
                fm.elidedText(
                    "  ".join(f"#{g}" for g in card["tags"]), Qt.TextElideMode.ElideRight, w
                ),
            )
        p.restore()


class KanbanColumn(QListWidget):
    dropped = Signal(list, object)  # (id-jevi zadataka, novi status)

    def __init__(self, status: TaskStatus, parent=None) -> None:
        super().__init__(parent)
        self.status = status
        self.setObjectName("KanbanColumn")
        self.setItemDelegate(CardDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self._drag_over = False

    def ids(self, items=None) -> list[str]:
        return [i.data(ROLE_ID) for i in (items if items is not None else self.selectedItems())]

    def _accepts(self, event) -> bool:
        return isinstance(event.source(), KanbanColumn) and event.source() is not self

    def dragEnterEvent(self, event) -> None:
        if self._accepts(event):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            self._set_drag_over(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._accepts(event):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_drag_over(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_drag_over(False)
        source = event.source()
        if not self._accepts(event):
            event.ignore()
            return
        ids = source.ids()
        event.setDropAction(Qt.DropAction.CopyAction)  # izvor ne briše stavke; sve se ponovo učita
        event.accept()
        if ids:
            self.dropped.emit(ids, self.status)

    def _set_drag_over(self, on: bool) -> None:
        self._drag_over = on
        self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drag_over:
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(theme.tokens().accent), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.viewport().rect()).adjusted(2, 2, -2, -2), 8, 8)
            p.end()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.doItemsLayout()  # visina kartica zavisi od širine


class ColumnFrame(QFrame):
    def __init__(self, status: TaskStatus, on_quick_add, parent=None) -> None:
        super().__init__(parent)
        self.status = status
        self.setObjectName("KanbanFrame")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        head = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {TASK_STATUS_COLOR[status]}; font-size: 10px;")
        title = QLabel(TASK_STATUS[status])
        title.setProperty("heading", True)
        self.count = QLabel("0")
        self.count.setProperty("muted", True)
        head.addWidget(dot)
        head.addWidget(title)
        head.addWidget(self.count)
        head.addStretch(1)
        lay.addLayout(head)
        self.list = KanbanColumn(status)
        lay.addWidget(self.list, 1)
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("+ Dodaj zadatak (Enter)")
        self.quick.returnPressed.connect(lambda: on_quick_add(self))
        lay.addWidget(self.quick)


class KanbanView(ProjectView):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        self.show_subtasks = QCheckBox("Prikaži podzadatke")
        self.show_subtasks.setChecked(True)
        self.show_subtasks.toggled.connect(lambda _c: self.refresh())
        bar.addWidget(self.show_subtasks)
        bar.addStretch(1)
        hint = QLabel(
            "Prevuci karticu u drugu kolonu da promeniš status · dupli klik otvara zadatak"
        )
        hint.setProperty("faint", True)
        bar.addWidget(hint)
        lay.addLayout(bar)

        cols = QHBoxLayout()
        cols.setSpacing(12)
        self.columns: dict[TaskStatus, ColumnFrame] = {}
        for status in TaskStatus:
            frame = ColumnFrame(status, self._quick_add)
            frame.list.dropped.connect(self._dropped)
            frame.list.itemDoubleClicked.connect(
                lambda item: open_task(self.ctx, item.data(ROLE_ID), self.window())
            )
            frame.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            frame.list.customContextMenuRequested.connect(
                lambda pos, lst=frame.list: self._menu(lst, pos)
            )
            self.columns[status] = frame
            cols.addWidget(frame, 1)
        lay.addLayout(cols, 1)
        theme.manager().changed.connect(self._style)
        self._style()

    def _style(self) -> None:
        t = theme.tokens()
        self.setStyleSheet(
            f"#KanbanFrame {{ background: {t.sidebar}; border: 1px solid {t.border};"
            f" border-radius: 10px; }}"
            "#KanbanColumn { background: transparent; border: none; }"
            "#KanbanColumn::item { background: transparent; border: none; }"
        )

    def reload(self) -> None:
        f = TaskFilter(search=self.ctx.search)
        today = date.today()
        with self.ctx.session() as s:
            rows = task_service.tree(s, self.ctx.project_id)
            titles = {task.id: task.title for task, _ in rows}
            cards: dict[TaskStatus, list[dict]] = {st: [] for st in TaskStatus}
            for task, depth in rows:
                if depth and not self.show_subtasks.isChecked():
                    continue
                if not task_service.matches(task, f, today):
                    continue
                cards[task.status].append(
                    {
                        "id": task.id,
                        "title": task.title,
                        "parent": titles.get(task.parent_id, ""),
                        "priority": task.priority,
                        "due": task.due_date.strftime("%d.%m.") if task.due_date else "",
                        "overdue": is_overdue(task, today),
                        "estimate": task.estimate_hours,
                        "progress": task.progress if 0 < task.progress < 100 else 0,
                        "tags": sorted(g.name for g in task.tags),
                        "done": task.status == TaskStatus.DONE,
                    }
                )
        for status, frame in self.columns.items():
            lst = frame.list
            lst.clear()
            for card in cards[status]:
                item = QListWidgetItem()
                item.setData(ROLE_ID, card["id"])
                item.setData(ROLE_CARD, card)
                item.setToolTip(card["title"])
                lst.addItem(item)
            frame.count.setText(str(len(cards[status])))

    def _dropped(self, ids: list[str], status: TaskStatus) -> None:
        def work(s):
            for tid in ids:
                task_service.set_status(s, task_service.get(s, tid), status)

        self.ctx.run(work, self.window())
        n = len(ids)
        self.ctx.notify(
            f"{'Zadatak premešten' if n == 1 else f'{n} zadataka premešteno'} u "
            f"„{TASK_STATUS[status]}“."
        )

    def _quick_add(self, frame: ColumnFrame) -> None:
        title = frame.quick.text().strip()
        if not title:
            return
        pid = self.ctx.project_id
        done = frame.status == TaskStatus.DONE
        created = self.ctx.run(
            lambda s: (
                task_service.create(
                    s, pid, title=title, status=frame.status, progress=100 if done else 0
                ).id
            ),
            self.window(),
        )
        if created:
            frame.quick.clear()

    def _menu(self, lst: KanbanColumn, pos) -> None:
        item = lst.itemAt(pos)
        if not item:
            return
        if not item.isSelected():
            lst.setCurrentItem(item)
        menu = QMenu(self)
        tid = item.data(ROLE_ID)
        menu.addAction(
            icons.icon("edit"), "Otvori…", lambda: open_task(self.ctx, tid, self.window())
        )
        move = menu.addMenu("Premesti u")
        for st, label in TASK_STATUS.items():
            if st != lst.status:
                move.addAction(label, lambda st=st: self._dropped(lst.ids(), st))
        menu.addSeparator()
        menu.addAction(icons.icon("trash"), "Obriši", lambda: self._delete(lst.ids()))
        menu.exec(lst.viewport().mapToGlobal(pos))

    def _delete(self, ids: list[str]) -> None:
        from PySide6.QtWidgets import QMessageBox

        if (
            QMessageBox.question(self.window(), "Obriši", f"Obrisati {len(ids)} zadatak(a)?")
            != QMessageBox.StandardButton.Yes
        ):
            return

        def work(s):
            for tid in ids:
                task = task_service.get(s, tid)
                if task is not None:
                    task_service.delete(s, task)

        self.ctx.run(work, self.window())
