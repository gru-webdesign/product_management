"""Zajedničko stanje UI-ja: izabrani projekat, pretraga i signal da su se podaci promenili.

Svaki prikaz sluša `data_changed` i sam ponovo čita šta mu treba iz baze (kratke sesije),
pa nema keširanih objekata koji zastarevaju.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import TypeVar

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget
from sqlalchemy.orm import Session

from app.db.base import Database

T = TypeVar("T")


class AppContext(QObject):
    project_changed = Signal(str)  # id projekta ili "" kad nijedan nije izabran
    data_changed = Signal()
    search_changed = Signal(str)
    message = Signal(str)  # kratka poruka za statusnu traku
    open_task_requested = Signal(str)
    timer_changed = Signal()
    show_dashboard = Signal()

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self.project_id: str = ""
        self.search: str = ""

    @contextmanager
    def session(self):
        with self.db.session() as s:
            yield s

    def run(self, fn: Callable[[Session], T], parent: QWidget | None = None) -> T | None:
        """Izvrši izmenu u jednoj transakciji; greška validacije prikaže se korisniku."""
        with self.db.session() as s:
            try:
                result = fn(s)
                s.commit()
            except ValueError as exc:
                s.rollback()
                QMessageBox.warning(parent, "Nije sačuvano", str(exc))
                return None
        self.data_changed.emit()
        return result

    def select_project(self, project_id: str) -> None:
        if project_id != self.project_id:
            self.project_id = project_id
            self.project_changed.emit(project_id)

    def set_search(self, text: str) -> None:
        text = text.strip()
        if text != self.search:
            self.search = text
            self.search_changed.emit(text)

    def notify(self, text: str) -> None:
        self.message.emit(text)
