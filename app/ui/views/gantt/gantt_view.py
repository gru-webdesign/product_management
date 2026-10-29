"""Prikaz Gant: traka sa alatima + grafikon; izmene sa grafikona idu kroz servise u bazu."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from app.db.models import Task, TaskDependency, TaskStatus
from app.labels import TASK_STATUS
from app.services import dependencies as dep_service
from app.services import milestones as ms_service
from app.services import tasks as task_service
from app.services.gantt_math import ZOOM_LABELS, ZOOMS
from app.services.tasks import TaskFilter, is_overdue
from app.ui import icons, theme
from app.ui.dialogs.milestone_dialog import edit_milestone
from app.ui.dialogs.task_dialog import open_task
from app.ui.views.base import ProjectView
from app.ui.views.gantt.chart import GanttChart
from app.ui.views.gantt.model import DepData, MilestoneData, RowData

ZOOM_ORDER = list(ZOOMS)  # day, week, month


class GanttView(ProjectView):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.zoom = "day"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.zoom_group = QButtonGroup(self)
        self.zoom_buttons: dict[str, QToolButton] = {}
        for key in ZOOM_ORDER:
            b = QToolButton()
            b.setText(ZOOM_LABELS[key])
            b.setCheckable(True)
            b.setChecked(key == self.zoom)
            b.clicked.connect(lambda _c=False, k=key: self.set_zoom(k))
            self.zoom_group.addButton(b)
            self.zoom_buttons[key] = b
            bar.addWidget(b)
        bar.addSpacing(6)
        today = QPushButton("Danas")
        today.setIcon(icons.icon("today", theme.tokens().today))
        today.clicked.connect(self.go_today)
        bar.addWidget(today)
        milestone = QPushButton("Milestone")
        milestone.setIcon(icons.icon("milestone"))
        milestone.clicked.connect(lambda: edit_milestone(self.ctx, None, self.window()))
        bar.addWidget(milestone)
        bar.addSpacing(6)
        self.show_cost = QCheckBox("Kolona troška")
        self.show_cost.toggled.connect(lambda _c: self.refresh())
        bar.addWidget(self.show_cost)
        self.show_done = QCheckBox("Završeni")
        self.show_done.setChecked(True)
        self.show_done.toggled.connect(lambda _c: self.refresh())
        bar.addWidget(self.show_done)
        bar.addStretch(1)
        hint = QLabel("Prevuci traku · ivica = trajanje · kružić → zavisnost · Ctrl+točkić = zum")
        hint.setProperty("faint", True)
        bar.addWidget(hint)
        lay.addLayout(bar)

        frame = QFrame()
        frame.setObjectName("Card")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        self.chart = GanttChart()
        fl.addWidget(self.chart)
        lay.addWidget(frame, 1)

        # Sve veze su „queued": obrada (upis u bazu, dijalog, meni) kreće tek kad se završi
        # događaj miša na traci. Osvežavanje grafikona briše i pravi trake iznova, pa traka ne sme
        # da bude obrisana dok se njen događaj još izvršava.
        c = self.chart
        queued = Qt.ConnectionType.QueuedConnection
        c.dates_committed.connect(self._dates_committed, queued)
        c.milestone_moved.connect(self._milestone_moved, queued)
        c.link_requested.connect(self._link, queued)
        c.open_task.connect(lambda tid: open_task(self.ctx, tid, self.window()), queued)
        c.open_milestone.connect(lambda mid: edit_milestone(self.ctx, mid, self.window()), queued)
        c.schedule_undated.connect(self._schedule_undated, queued)
        c.task_menu.connect(self._task_menu, queued)
        c.dependency_menu.connect(self._dependency_menu, queued)
        c.zoom_step.connect(self._zoom_step, queued)
        theme.manager().changed.connect(lambda: self.chart.viewport().update())

    # --- podaci ----------------------------------------------------------------------------------

    def reload(self) -> None:
        f = TaskFilter(search=self.ctx.search, hide_done=not self.show_done.isChecked())
        today = date.today()
        with self.ctx.session() as s:
            tree = task_service.tree(s, self.ctx.project_id)
            parents = {t.parent_id for t, _ in tree if t.parent_id}
            rows = [
                RowData(
                    task_id=t.id,
                    title=t.title,
                    depth=depth,
                    start=t.start_date or t.due_date,
                    end=t.due_date or t.start_date,
                    progress=100 if t.status == TaskStatus.DONE else t.progress,
                    status=t.status,
                    priority=t.priority,
                    has_children=t.id in parents,
                    overdue=is_overdue(t, today),
                    cost_minor=t.planned_cost_minor,
                )
                for t, depth in tree
                if task_service.matches(t, f, today)
            ]
            shown = {r.task_id for r in rows}
            milestones = [
                MilestoneData(m.id, m.name, m.date, m.done)
                for m in ms_service.for_project(s, self.ctx.project_id)
            ]
            deps = [
                DepData(d.id, d.predecessor_id, d.successor_id, d.type, d.lag_days)
                for d in dep_service.for_project(s, self.ctx.project_id)
                if d.predecessor_id in shown and d.successor_id in shown
            ]
            from app.services import projects as project_service

            p = project_service.get(s, self.ctx.project_id)
            extra = [d for d in (p.start_date, p.end_date) if d] if p else []
        self.chart.set_data(rows, milestones, deps, self.zoom, self.show_cost.isChecked(), extra)

    def set_zoom(self, zoom: str) -> None:
        if zoom == self.zoom:
            return
        self.zoom = zoom
        self.zoom_buttons[zoom].setChecked(True)
        self.refresh()

    def _zoom_step(self, step: int) -> None:
        i = ZOOM_ORDER.index(self.zoom) - step  # točkić gore = bliže (dan)
        self.set_zoom(ZOOM_ORDER[max(0, min(len(ZOOM_ORDER) - 1, i))])

    def go_today(self) -> None:
        self.chart.scroll_to(date.today(), center=True)

    # --- izmene ----------------------------------------------------------------------------------

    def _dates_committed(self, task_id: str, start: date, end: date) -> None:
        moved = self.ctx.run(
            lambda s: [
                t.title for t in task_service.set_dates(s, task_service.get(s, task_id), start, end)
            ],
            self.window(),
        )
        if moved:
            self.ctx.notify(
                f"Datumi sačuvani. Zbog zavisnosti pomereno još {len(moved)}: "
                + ", ".join(moved[:3])
                + ("…" if len(moved) > 3 else "")
            )
        elif moved is not None:
            self.ctx.notify("Datumi sačuvani.")
        else:
            self.refresh()  # greška: vrati traku na staro mesto

    def _milestone_moved(self, milestone_id: str, day: date) -> None:
        from app.db.models import Milestone

        self.ctx.run(
            lambda s: ms_service.update(s, s.get(Milestone, milestone_id), date=day), self.window()
        )

    def _link(self, predecessor_id: str, successor_id: str) -> None:
        def work(s):
            pred, succ = s.get(Task, predecessor_id), s.get(Task, successor_id)
            dep_service.add(s, pred, succ)
            return succ.title

        title = self.ctx.run(work, self.window())
        if title:
            self.ctx.notify(f"Zavisnost dodata: „{title}“ čeka na prethodni zadatak.")
        else:
            self.refresh()

    def _schedule_undated(self, task_id: str, day: date) -> None:
        self.ctx.run(
            lambda s: task_service.set_dates(
                s, task_service.get(s, task_id), day, day + timedelta(days=2)
            ),
            self.window(),
        )

    def _task_menu(self, task_id: str, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction(
            icons.icon("edit"), "Otvori…", lambda: open_task(self.ctx, task_id, self.window())
        )
        status = menu.addMenu("Status")
        for st, label in TASK_STATUS.items():
            status.addAction(
                label,
                lambda st=st: self.ctx.run(
                    lambda s: task_service.set_status(s, task_service.get(s, task_id), st)
                ),
            )
        shift = menu.addMenu("Pomeri")
        for days, label in ((-7, "−1 nedelja"), (-1, "−1 dan"), (1, "+1 dan"), (7, "+1 nedelja")):
            shift.addAction(
                label,
                lambda d=days: self.ctx.run(
                    lambda s: task_service.move_by_days(s, task_service.get(s, task_id), d),
                    self.window(),
                ),
            )
        menu.addAction(
            "Ukloni datume",
            lambda: self.ctx.run(
                lambda s: task_service.set_dates(s, task_service.get(s, task_id), None, None)
            ),
        )
        menu.exec(pos)

    def _dependency_menu(self, dep_id: str, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction(
            icons.icon("x"),
            "Ukloni zavisnost",
            lambda: self.ctx.run(
                lambda s: dep_service.remove(s, s.get(TaskDependency, dep_id)), self.window()
            ),
        )
        menu.exec(pos)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            for item in self.chart.scene().selectedItems():
                dep = getattr(item, "dep", None)
                if isinstance(dep, DepData):
                    self.ctx.run(
                        lambda s, d=dep: dep_service.remove(s, s.get(TaskDependency, d.id))
                    )
                    return
        super().keyPressEvent(event)
