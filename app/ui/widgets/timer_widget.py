"""Tajmer u statusnoj traci: naziv zadatka, proteklo vreme i dugme Zaustavi."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.services import timetracking as tt
from app.ui import icons, theme
from app.ui.context import AppContext


def start_timer(ctx: AppContext, task_id: str, parent=None) -> None:
    stopped = ctx.run(lambda s: tt.start(s, task_id), parent)
    ctx.timer_changed.emit()
    if stopped:
        ctx.notify(
            f"Prethodni tajmer je zaustavljen i upisano je {tt.format_hours(stopped.hours)}."
        )
    else:
        ctx.notify("Tajmer je pokrenut.")


def stop_timer(ctx: AppContext, parent=None) -> None:
    entry = ctx.run(lambda s: tt.stop(s), parent)
    ctx.timer_changed.emit()
    if entry:
        ctx.notify(f"Upisano je {tt.format_hours(entry.hours)} na zadatak.")
    else:
        ctx.notify("Tajmer je zaustavljen. Kraće od minuta se ne upisuje.")


class TimerWidget(QWidget):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)
        self.icon = QLabel()
        self.title = QLabel()
        self.title.setMaximumWidth(260)
        self.elapsed = QLabel()
        self.elapsed.setFont(theme.mono(self.font()))
        self.stop_button = QPushButton("Zaustavi")
        self.stop_button.setIcon(icons.icon("stop"))
        self.stop_button.clicked.connect(lambda: stop_timer(self.ctx, self.window()))
        for w in (self.icon, self.title, self.elapsed, self.stop_button):
            lay.addWidget(w)
        self._running: tt.RunningTimer | None = None
        self._tick = QTimer(self, interval=1000)
        self._tick.timeout.connect(self._update)
        ctx.timer_changed.connect(self.reload)
        ctx.data_changed.connect(self.reload)
        theme.manager().changed.connect(self.reload)
        self.reload()

    def reload(self) -> None:
        with self.ctx.session() as s:
            self._running = tt.running(s)
        on = self._running is not None
        self.setVisible(on)
        if on:
            self.icon.setPixmap(icons.icon("timer", theme.tokens().accent).pixmap(16, 16))
            fm = self.title.fontMetrics()
            from PySide6.QtCore import Qt

            self.title.setText(fm.elidedText(self._running.title, Qt.TextElideMode.ElideRight, 250))
            self.title.setToolTip(self._running.title)
            self._tick.start()
            self._update()
        else:
            self._tick.stop()

    def _update(self) -> None:
        if self._running:
            self.elapsed.setText(tt.format_duration(self._running.elapsed()))
