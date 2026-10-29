"""Podaci koje Gant prikazuje (čisti podaci, bez ORM objekata i bez Qt-a)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.db.models import DependencyType, Priority, TaskStatus

HEADER_H = 54
ROW_H = 34
BAR_H = 18
LEFT_W = 300
COST_W = 110
HANDLE_R = 5


@dataclass
class RowData:
    task_id: str
    title: str
    depth: int
    start: date | None
    end: date | None
    progress: int
    status: TaskStatus
    priority: Priority
    has_children: bool
    overdue: bool
    cost_minor: int

    @property
    def dated(self) -> bool:
        return self.start is not None and self.end is not None

    @property
    def done(self) -> bool:
        return self.status == TaskStatus.DONE


@dataclass
class MilestoneData:
    id: str
    name: str
    date: date
    done: bool


@dataclass
class DepData:
    id: str
    predecessor_id: str
    successor_id: str
    type: DependencyType
    lag_days: int
