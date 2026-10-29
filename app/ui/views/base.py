"""Osnova za prikaze projekta (Lista, Kanban, Gant, Budžet).

Prikaz se osvežava samo kad je vidljiv; skrivenom se samo označi da je zastareo.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.ui.context import AppContext


class ProjectView(QWidget):
    title = ""
    icon_name = ""

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._stale = True
        ctx.project_changed.connect(lambda _pid: self.mark_stale())
        ctx.data_changed.connect(self.mark_stale)
        ctx.search_changed.connect(lambda _t: self.mark_stale())

    def mark_stale(self) -> None:
        self._stale = True
        if self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        if not self.ctx.project_id:
            return
        self._stale = False
        self.reload()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._stale:
            self.refresh()

    def reload(self) -> None:  # pragma: no cover - podklase
        raise NotImplementedError
