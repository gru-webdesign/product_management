"""Gant: pravo prevlačenje mišem po grafikonu (pomeranje, trajanje, povezivanje)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from app.services import dependencies as dep_service
from app.services import milestones as ms_service
from app.services import tasks as task_service
from app.ui.main_window import MainWindow
from app.ui.views.gantt.gantt_view import GanttView
from app.ui.views.gantt.items import TaskBarItem
from scripts.seed_demo import seed


@pytest.fixture
def gantt(qtbot, db):
    with db.session() as s:
        seed(s, today=date.today())
        s.commit()
    w = MainWindow(db)
    w.resize(1500, 900)
    qtbot.addWidget(w)
    w.show()
    w.tabs.setCurrentIndex(2)
    view = w.views[2]
    assert isinstance(view, GanttView)
    QApplication.processEvents()
    return w, view


def task_id(w, title):
    with w.db.session() as s:
        return next(t.id for t, _ in task_service.tree(s, w.ctx.project_id) if t.title == title)


def get(w, tid):
    with w.db.session() as s:
        t = task_service.get(s, tid)
        return t.start_date, t.due_date


def send(widget, kind, pos: QPointF, buttons=Qt.MouseButton.LeftButton):
    button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else Qt.MouseButton.NoButton
    if kind == QEvent.Type.MouseButtonRelease:
        buttons = Qt.MouseButton.NoButton
    ev = QMouseEvent(
        kind,
        pos,
        widget.mapToGlobal(pos.toPoint()).toPointF(),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, ev)
    QApplication.processEvents()


def drag(chart, start_scene: QPointF, end_scene: QPointF, steps: int = 6):
    vp = chart.viewport()
    a = QPointF(chart.mapFromScene(start_scene))
    b = QPointF(chart.mapFromScene(end_scene))
    send(vp, QEvent.Type.MouseMove, a, Qt.MouseButton.NoButton)
    send(vp, QEvent.Type.MouseButtonPress, a)
    for i in range(1, steps + 1):
        send(vp, QEvent.Type.MouseMove, a + (b - a) * (i / steps))
    send(vp, QEvent.Type.MouseButtonRelease, b)
    for _ in range(3):  # queued obrada posle puštanja miša
        QApplication.processEvents()


def visible(chart, bar: TaskBarItem):
    chart.scroll_to(bar.start - timedelta(days=2))
    QApplication.processEvents()


def test_rows_bars_and_dependencies_drawn(gantt):
    _, view = gantt
    chart = view.chart
    assert len(chart.rows) == 10
    assert len(chart.bars) == 10
    assert len(chart.dep_items) == 8
    assert len(chart.milestones) == 2


def test_drag_moves_task_and_pushes_successors(gantt):
    w, view = gantt
    chart = view.chart
    tid = task_id(w, "Odobrenje klijenta")
    dev = task_id(w, "Izrada sajta")
    s0, e0 = get(w, tid)
    dev0 = get(w, dev)
    bar = chart.bars[tid]
    visible(chart, bar)
    r = bar.bar_rect()
    start = QPointF(r.center().x(), r.center().y())
    drag(chart, start, start + QPointF(3 * chart.scale.px_per_day, 0))
    assert get(w, tid) == (s0 + timedelta(days=3), e0 + timedelta(days=3))
    assert get(w, dev)[0] == dev0[0] + timedelta(days=3)  # zavisni zadatak pomeren


def test_drag_right_edge_changes_duration(gantt):
    w, view = gantt
    chart = view.chart
    tid = task_id(w, "Objava i obuka")
    s0, e0 = get(w, tid)
    bar = chart.bars[tid]
    visible(chart, bar)
    r = bar.bar_rect()
    edge = QPointF(r.right() - 2, r.center().y())
    drag(chart, edge, edge + QPointF(2 * chart.scale.px_per_day, 0))
    assert get(w, tid) == (s0, e0 + timedelta(days=2))


def test_link_handle_creates_dependency(gantt):
    w, view = gantt
    chart = view.chart
    a = task_id(w, "Brief i prikupljanje sadržaja")
    b = task_id(w, "Objava i obuka")
    bar_a, bar_b = chart.bars[a], chart.bars[b]
    visible(chart, bar_a)
    # hover otkriva kružić za povezivanje
    send(
        chart.viewport(),
        QEvent.Type.MouseMove,
        QPointF(chart.mapFromScene(bar_a.bar_rect().center())),
        Qt.MouseButton.NoButton,
    )
    handle = bar_a.handle_center()
    target = QPointF(handle.x() + 40, bar_b.bar_rect().center().y())
    drag(chart, handle, target)
    with w.db.session() as s:
        succ = [
            d.successor_id
            for d in dep_service.for_project(s, w.ctx.project_id)
            if d.predecessor_id == a
        ]
    assert b in succ


def test_zoom_and_today(gantt):
    _, view = gantt
    view.set_zoom("week")
    assert view.chart.scale.px_per_day == 16.0
    view._zoom_step(-1)
    assert view.zoom == "month"
    view._zoom_step(1)
    view._zoom_step(1)
    assert view.zoom == "day"
    view.go_today()
    view.show_cost.setChecked(True)
    assert view.chart.left_w > 300


def test_milestone_move_and_undated_scheduling(gantt):
    w, view = gantt
    with w.db.session() as s:
        m = ms_service.for_project(s, w.ctx.project_id)[0]
        mid, day = m.id, m.date
    view._milestone_moved(mid, day + timedelta(days=1))
    with w.db.session() as s:
        assert ms_service.for_project(s, w.ctx.project_id)[0].date == day + timedelta(days=1)

    tid = task_id(w, "Testiranje na telefonima")
    w.ctx.run(lambda s: task_service.set_dates(s, task_service.get(s, tid), None, None))
    assert tid not in view.chart.bars
    view._schedule_undated(tid, date.today())
    assert get(w, tid) == (date.today(), date.today() + timedelta(days=2))
    assert tid in view.chart.bars


def test_cycle_link_rejected_without_crash(gantt, monkeypatch):
    w, view = gantt
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    a = task_id(w, "Brief i prikupljanje sadržaja")
    z = task_id(w, "Objava i obuka")
    view._link(z, a)  # Objava → Brief bi napravila krug
    assert shown and "krug" in shown[0]
