"""Podsetnici za rokove kao sistemske notifikacije (ikonica u Windows sistemskoj traci).

Provera pri pokretanju i na svakih 30 minuta. Klik na notifikaciju otvara aplikaciju na
projektu prvog podsetnika.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app import APP_NAME
from app.services import reminders
from app.ui.context import AppContext

INTERVAL_MS = 30 * 60 * 1000


class ReminderManager(QObject):
    def __init__(self, ctx: AppContext, window, icon: QIcon) -> None:
        super().__init__(window)
        self.ctx = ctx
        self.window = window
        self.last: list[reminders.Reminder] = []
        self.tray: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.setToolTip(APP_NAME)
            menu = QMenu()
            menu.addAction("Otvori", self._bring_up)
            menu.addAction("Proveri rokove", lambda: self.check(force=True))
            menu.addSeparator()
            menu.addAction("Izlaz", QApplication.instance().quit)
            self.tray.setContextMenu(menu)
            self._menu = menu
            self.tray.messageClicked.connect(self._open_first)
            self.tray.activated.connect(
                lambda reason: (
                    self._bring_up() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
                )
            )
            self.tray.show()
        self.timer = QTimer(self, interval=INTERVAL_MS)
        self.timer.timeout.connect(self.check)
        self.timer.start()

    def check(self, force: bool = False) -> list[reminders.Reminder]:
        """Prikazuje nove podsetnike. force=True prikazuje i one već viđene danas."""
        with self.ctx.session() as s:
            if not reminders.enabled(s) and not force:
                return []
            items = reminders.due(s) if force else reminders.pending(s)
            if items:
                reminders.mark_sent(s, items)
                s.commit()
        self.last = items
        if not items:
            if force:
                self.ctx.notify("Nema rokova danas ni sutra.")
            return items
        title, body = reminders.summarize(items)
        if self.tray is not None and self.tray.supportsMessages():
            self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 12000)
        self.ctx.notify(f"{title}. Otvori Pregled za detalje.")
        return items

    def _bring_up(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _open_first(self) -> None:
        self._bring_up()
        first = next((r for r in self.last if r.task_id), None) or (
            self.last[0] if self.last else None
        )
        if first is None:
            return
        self.ctx.open_project(first.project_id)
        if first.task_id:
            self.ctx.open_task_requested.emit(first.task_id)

    def shutdown(self) -> None:
        self.timer.stop()
        if self.tray is not None:
            self.tray.hide()
