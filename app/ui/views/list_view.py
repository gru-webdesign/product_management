"""Prikaz Lista: zadaci kao stablo (podzadaci ispod roditelja) sa filterima i sortiranjem."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.db.models import Priority, TaskStatus
from app.labels import PRIORITY, PRIORITY_COLOR, TASK_STATUS, TASK_STATUS_COLOR
from app.services import tasks as task_service
from app.services.money import format_money
from app.services.tasks import TaskFilter, is_overdue
from app.ui import icons, theme
from app.ui.dialogs.task_dialog import open_new_task, open_task
from app.ui.views.base import ProjectView
from app.ui.widgets.paint import PillDelegate, ProgressDelegate

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_SORT = Qt.ItemDataRole.UserRole + 2

COLUMNS = [
    "Naziv",
    "Status",
    "Prioritet",
    "Početak",
    "Rok",
    "Progres",
    "Procena",
    "Trošak",
    "Tagovi",
]
C_TITLE, C_STATUS, C_PRIO, C_START, C_DUE, C_PROGRESS, C_EST, C_COST, C_TAGS = range(9)


class TaskItem(QTreeWidgetItem):
    """Sortiranje po pravoj vrednosti (datum, broj), ne po prikazanom tekstu."""

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        a, b = self.data(col, ROLE_SORT), other.data(col, ROLE_SORT)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m.%Y.") if d else ""


class ListView(ProjectView):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Svi statusi", None)
        for st, label in TASK_STATUS.items():
            self.status_filter.addItem(label, st)
        self.priority_filter = QComboBox()
        self.priority_filter.addItem("Svi prioriteti", None)
        for pr, label in PRIORITY.items():
            self.priority_filter.addItem(label, pr)
        self.due_filter = QComboBox()
        for key, label in (
            ("", "Svi rokovi"),
            ("overdue", "Kasne"),
            ("week", "Narednih 7 dana"),
            ("none", "Bez roka"),
        ):
            self.due_filter.addItem(label, key)
        self.tag_filter = QComboBox()
        self.hide_done = QCheckBox("Sakrij završene")
        self.clear_button = QPushButton("Poništi filtere")
        self.clear_button.setProperty("flat", True)
        self.clear_button.clicked.connect(self.clear_filters)
        for w in (self.status_filter, self.priority_filter, self.due_filter, self.tag_filter):
            w.currentIndexChanged.connect(lambda _i: self.refresh())
            bar.addWidget(w)
        self.hide_done.toggled.connect(lambda _c: self.refresh())
        bar.addWidget(self.hide_done)
        bar.addWidget(self.clear_button)
        bar.addStretch(1)
        self.count_label = QLabel()
        self.count_label.setProperty("muted", True)
        bar.addWidget(self.count_label)
        lay.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSortingEnabled(False)
        self.tree.setIndentation(18)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemActivated.connect(lambda item, _c: self._edit_later(item))
        self.tree.setItemDelegateForColumn(C_STATUS, PillDelegate(self.tree))
        self.tree.setItemDelegateForColumn(C_PRIO, PillDelegate(self.tree))
        self.tree.setItemDelegateForColumn(C_PROGRESS, ProgressDelegate(self.tree))
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(C_TITLE, QHeaderView.ResizeMode.Stretch)
        for col, width in (
            (C_STATUS, 130),
            (C_PRIO, 105),
            (C_START, 100),
            (C_DUE, 100),
            (C_PROGRESS, 130),
            (C_EST, 80),
            (C_COST, 120),
            (C_TAGS, 150),
        ):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.tree.setColumnWidth(col, width)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._sort_clicked)
        self._sort_col: int | None = None
        self._sort_order = Qt.SortOrder.AscendingOrder
        lay.addWidget(self.tree, 1)

        self.empty = QLabel("Nema zadataka. Dodaj prvi dugmetom „Zadatak“ ili Ctrl+N.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setProperty("muted", True)
        self.empty.hide()
        lay.addWidget(self.empty)

        for text, key, slot in (
            ("Obriši", QKeySequence.StandardKey.Delete, self.delete_selected),
            ("Uredi", QKeySequence("F2"), lambda: self.edit(self.current())),
        ):
            action = QAction(text, self.tree)
            action.setShortcut(key)
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
            action.triggered.connect(slot)
            self.tree.addAction(action)

    # --- filteri ---------------------------------------------------------------------------------

    def current_filter(self) -> TaskFilter:
        return TaskFilter(
            search=self.ctx.search,
            status=self.status_filter.currentData(),
            priority=self.priority_filter.currentData(),
            due=self.due_filter.currentData() or "",
            tag=self.tag_filter.currentData() or "",
            hide_done=self.hide_done.isChecked(),
        )

    def clear_filters(self) -> None:
        for w in (self.status_filter, self.priority_filter, self.due_filter, self.tag_filter):
            w.blockSignals(True)
            w.setCurrentIndex(0)
            w.blockSignals(False)
        self.hide_done.blockSignals(True)
        self.hide_done.setChecked(False)
        self.hide_done.blockSignals(False)
        self.refresh()

    def _reload_tags(self, tags: list[str]) -> None:
        current = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("Svi tagovi", "")
        for t in tags:
            self.tag_filter.addItem(f"#{t}", t)
        idx = self.tag_filter.findData(current) if current else 0
        self.tag_filter.setCurrentIndex(max(0, idx))
        self.tag_filter.blockSignals(False)

    # --- punjenje --------------------------------------------------------------------------------

    def reload(self) -> None:
        f = self.current_filter()
        expanded = self._expanded_ids()
        selected = {i.data(C_TITLE, ROLE_ID) for i in self.tree.selectedItems()}
        today = date.today()
        t = theme.tokens()
        with self.ctx.session() as s:
            self._reload_tags(task_service.all_tags(s))
            rows = task_service.tree(s, self.ctx.project_id)
            flat = f.active()
            visible = [(task, d) for task, d in rows if task_service.matches(task, f, today)]
            parents = {task.id: task.title for task, _ in rows}
            data = [
                self._row(task, depth, parents, today)
                for task, depth in (visible if flat else rows)
            ]
            total = len(rows)

        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        items: dict[str, TaskItem] = {}
        bold = QFont(self.tree.font())
        bold.setWeight(QFont.Weight.Medium)
        for row in data:
            item = TaskItem()
            parent_item = None if flat else items.get(row["parent_id"])
            (parent_item.addChild(item) if parent_item else self.tree.addTopLevelItem(item))
            items[row["id"]] = item
            item.setData(C_TITLE, ROLE_ID, row["id"])
            title = row["title"]
            if flat and row["parent_title"]:
                title = f"{row['parent_title']}  ›  {title}"
            item.setText(C_TITLE, title)
            item.setData(C_TITLE, ROLE_SORT, row["order"])
            if row["depth"] == 0 and not flat:
                item.setFont(C_TITLE, bold)
            if row["done"]:
                item.setForeground(C_TITLE, QColor(t.faint))
            item.setText(C_STATUS, TASK_STATUS[row["status"]])
            item.setData(C_STATUS, PillDelegate.COLOR_ROLE, TASK_STATUS_COLOR[row["status"]])
            item.setData(C_STATUS, ROLE_SORT, list(TASK_STATUS).index(row["status"]))
            item.setText(C_PRIO, PRIORITY[row["priority"]])
            item.setData(C_PRIO, PillDelegate.COLOR_ROLE, PRIORITY_COLOR[row["priority"]])
            item.setData(C_PRIO, ROLE_SORT, list(PRIORITY).index(row["priority"]))
            item.setText(C_START, _fmt(row["start"]))
            item.setData(C_START, ROLE_SORT, row["start"] or date.max)
            item.setText(C_DUE, _fmt(row["due"]))
            item.setData(C_DUE, ROLE_SORT, row["due"] or date.max)
            if row["overdue"]:
                item.setForeground(C_DUE, QColor(t.danger))
                item.setToolTip(C_DUE, "Rok je prošao")
            item.setData(C_PROGRESS, ProgressDelegate.VALUE_ROLE, row["progress"])
            item.setData(C_PROGRESS, ROLE_SORT, row["progress"])
            if row["estimate"]:
                item.setText(C_EST, f"{row['estimate']:g} h")
            item.setData(C_EST, ROLE_SORT, row["estimate"] or 0)
            item.setTextAlignment(
                C_EST, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if row["cost"]:
                item.setText(C_COST, format_money(row["cost"]))
            item.setData(C_COST, ROLE_SORT, row["cost"])
            item.setTextAlignment(
                C_COST, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            item.setText(C_TAGS, "  ".join(f"#{x}" for x in row["tags"]))
            item.setForeground(C_TAGS, QColor(t.muted))
            if row["id"] in selected:
                item.setSelected(True)
        for task_id, item in items.items():
            if item.childCount():
                item.setExpanded(task_id in expanded or not self._seen)
        self._seen = True
        if self._sort_col is not None:
            self.tree.sortItems(self._sort_col, self._sort_order)
        self.tree.setUpdatesEnabled(True)

        shown = len(data)
        self.count_label.setText(f"{shown} od {total}" if flat else f"{total} zadataka")
        self.clear_button.setVisible(flat)
        self.empty.setVisible(total == 0)
        self.tree.setVisible(total > 0)
        if total and not shown:
            self.count_label.setText("Nijedan zadatak ne odgovara filterima")

    _seen = False

    @staticmethod
    def _row(task, depth, parents, today) -> dict:
        return {
            "id": task.id,
            "parent_id": task.parent_id,
            "parent_title": parents.get(task.parent_id, ""),
            "title": task.title,
            "depth": depth,
            "order": task.sort_order,
            "status": task.status,
            "priority": task.priority,
            "start": task.start_date,
            "due": task.due_date,
            "overdue": is_overdue(task, today),
            "done": task.status == TaskStatus.DONE,
            "progress": 100 if task.status == TaskStatus.DONE else task.progress,
            "estimate": task.estimate_hours,
            "cost": task.planned_cost_minor,
            "tags": sorted(tg.name for tg in task.tags),
        }

    def _expanded_ids(self) -> set[str]:
        out = set()
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it.isExpanded():
                out.add(it.data(C_TITLE, ROLE_ID))
            stack.extend(it.child(i) for i in range(it.childCount()))
        return out

    def _sort_clicked(self, col: int) -> None:
        if self._sort_col == col:
            if self._sort_order == Qt.SortOrder.AscendingOrder:
                self._sort_order = Qt.SortOrder.DescendingOrder
            else:  # treći klik vraća ručni redosled
                self._sort_col = None
                self.tree.header().setSortIndicatorShown(False)
                self.refresh()
                return
        else:
            self._sort_col, self._sort_order = col, Qt.SortOrder.AscendingOrder
        self.tree.header().setSortIndicatorShown(True)
        self.tree.header().setSortIndicator(col, self._sort_order)
        self.tree.sortItems(col, self._sort_order)

    # --- akcije ----------------------------------------------------------------------------------

    def current(self) -> QTreeWidgetItem | None:
        return self.tree.currentItem()

    def selected_ids(self) -> list[str]:
        return [i.data(C_TITLE, ROLE_ID) for i in self.tree.selectedItems()]

    def _edit_later(self, item: QTreeWidgetItem) -> None:
        # Dijalog se otvara posle dvoklika: čuvanje osvežava stablo i briše ovu stavku.
        tid = item.data(C_TITLE, ROLE_ID)
        QTimer.singleShot(0, lambda: open_task(self.ctx, tid, self.window()))

    def edit(self, item: QTreeWidgetItem | None) -> None:
        if item:
            open_task(self.ctx, item.data(C_TITLE, ROLE_ID), self.window())

    def set_status(self, status: TaskStatus) -> None:
        ids = self.selected_ids()

        def work(s):
            for tid in ids:
                task_service.set_status(s, task_service.get(s, tid), status)

        self.ctx.run(work, self.window())

    def set_priority(self, priority: Priority) -> None:
        ids = self.selected_ids()

        def work(s):
            for tid in ids:
                task_service.update(s, task_service.get(s, tid), priority=priority)

        self.ctx.run(work, self.window())

    def move(self, direction: int) -> None:
        item = self.current()
        if item:
            tid = item.data(C_TITLE, ROLE_ID)
            self.ctx.run(lambda s: task_service.move(s, task_service.get(s, tid), direction))

    def delete_selected(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        ids = self.selected_ids()
        if not ids:
            return
        text = "Obrisati izabrani zadatak?" if len(ids) == 1 else f"Obrisati {len(ids)} zadataka?"
        if (
            QMessageBox.question(
                self.window(), "Obriši", text + "\nPodzadaci se brišu zajedno sa roditeljem."
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        def work(s):
            for tid in ids:
                task = task_service.get(s, tid)
                if task is not None:  # možda je već obrisan kao podzadatak
                    task_service.delete(s, task)

        self.ctx.run(work, self.window())

    def _menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        if item:
            if not item.isSelected():
                self.tree.setCurrentItem(item)
            menu.addAction(icons.icon("edit"), "Uredi…", lambda: self.edit(item))
            tid = item.data(C_TITLE, ROLE_ID)
            menu.addAction(
                icons.icon("plus"),
                "Dodaj podzadatak…",
                lambda: open_new_task(self.ctx, self.window(), parent_id=tid),
            )
            status_menu = menu.addMenu("Status")
            for st, label in TASK_STATUS.items():
                status_menu.addAction(label, lambda st=st: self.set_status(st))
            prio_menu = menu.addMenu("Prioritet")
            for pr, label in PRIORITY.items():
                prio_menu.addAction(label, lambda pr=pr: self.set_priority(pr))
            if self._sort_col is None and not self.current_filter().active():
                menu.addSeparator()
                menu.addAction("Pomeri gore", lambda: self.move(-1))
                menu.addAction("Pomeri dole", lambda: self.move(1))
            menu.addSeparator()
            menu.addAction(icons.icon("trash"), "Obriši", self.delete_selected)
        else:
            menu.addAction(
                icons.icon("plus"), "Novi zadatak…", lambda: open_new_task(self.ctx, self.window())
            )
        menu.exec(self.tree.viewport().mapToGlobal(pos))
