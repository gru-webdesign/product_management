"""Rad u pozadini (mreža) bez blokiranja prozora. Rezultat se vraća u glavnu nit preko signala.

Funkcija dobija sopstvenu sesiju baze (SQLite konekcije se ne dele između niti).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.db.base import Database

_alive: set[_Job] = set()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Job(QRunnable):
    def __init__(self, db: Database, fn: Callable[[Any], Any]) -> None:
        super().__init__()
        self.db = db
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            with self.db.session() as s:
                result = self.fn(s)
                s.commit()
        except Exception as exc:  # poruka ide korisniku, ne ruši aplikaciju
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.signals.done.emit(result)
        finally:
            _alive.discard(self)


def run(
    db: Database,
    fn: Callable[[Any], Any],
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> _Job:
    job = _Job(db, fn)
    if on_done:
        job.signals.done.connect(on_done)
    if on_error:
        job.signals.failed.connect(on_error)
    _alive.add(job)
    QThreadPool.globalInstance().start(job)
    return job


def wait_all(timeout_ms: int = 10000) -> bool:
    return QThreadPool.globalInstance().waitForDone(timeout_ms)
