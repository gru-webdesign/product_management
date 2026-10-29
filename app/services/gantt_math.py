"""Matematika Gant grafikona: datum ↔ piksel, zum, opseg prikaza i oznake na osi (bez Qt-a)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

ZOOMS: dict[str, float] = {"day": 38.0, "week": 16.0, "month": 5.0}
ZOOM_LABELS = {"day": "Dan", "week": "Nedelja", "month": "Mesec"}

MONTHS = [
    "januar",
    "februar",
    "mart",
    "april",
    "maj",
    "jun",
    "jul",
    "avgust",
    "septembar",
    "oktobar",
    "novembar",
    "decembar",
]
MONTHS_SHORT = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"]
WEEKDAYS = ["P", "U", "S", "Č", "P", "S", "N"]  # pon … ned


@dataclass(frozen=True)
class Tick:
    x: float
    width: float
    label: str
    strong: bool = False  # deblja linija (početak meseca / nedelje)


@dataclass(frozen=True)
class TimeScale:
    origin: date
    days: int
    px_per_day: float

    @property
    def width(self) -> float:
        return self.days * self.px_per_day

    @property
    def end(self) -> date:
        return self.origin + timedelta(days=self.days)

    def x(self, d: date) -> float:
        return (d - self.origin).days * self.px_per_day

    def x_end(self, d: date) -> float:
        """Desna ivica dana (traka do datuma uključuje ceo taj dan)."""
        return self.x(d) + self.px_per_day

    def date_at(self, x: float) -> date:
        return self.origin + timedelta(days=math.floor(x / self.px_per_day))

    def days_for(self, dx: float) -> int:
        return round(dx / self.px_per_day)

    def contains(self, d: date) -> bool:
        return self.origin <= d < self.end


def visible_range(
    dates: Iterable[date | None], today: date, zoom: str = "day"
) -> tuple[date, date]:
    """Opseg prikaza: od nedelju dana pre najranijeg datuma (od ponedeljka) do posle najkasnijeg."""
    known = [d for d in dates if d is not None] + [today]
    start, end = min(known), max(known)
    pad_before = {"day": 7, "week": 14, "month": 31}[zoom]
    pad_after = {"day": 21, "week": 42, "month": 92}[zoom]
    start -= timedelta(days=pad_before)
    start -= timedelta(days=start.weekday())  # ponedeljak
    if zoom == "month":
        start = start.replace(day=1)
    end += timedelta(days=pad_after)
    min_days = {"day": 42, "week": 120, "month": 365}[zoom]
    if (end - start).days < min_days:
        end = start + timedelta(days=min_days)
    return start, end


def make_scale(dates: Iterable[date | None], today: date, zoom: str = "day") -> TimeScale:
    start, end = visible_range(dates, today, zoom)
    return TimeScale(start, (end - start).days, ZOOMS[zoom])


def _month_ticks(scale: TimeScale, short: bool = False, with_year: bool = True) -> list[Tick]:
    ticks = []
    d = scale.origin.replace(day=1)
    while d < scale.end:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        x0 = max(0.0, scale.x(d))
        x1 = min(scale.width, scale.x(nxt))
        name = (MONTHS_SHORT if short else MONTHS)[d.month - 1]
        label = f"{name} {d.year}" if with_year else name
        ticks.append(Tick(x0, x1 - x0, label, strong=True))
        d = nxt
    return ticks


def header_ticks(scale: TimeScale, zoom: str) -> tuple[list[Tick], list[Tick]]:
    """Dva reda oznaka: (gornji, donji)."""
    if zoom == "day":
        top = _month_ticks(scale)
        bottom = []
        for i in range(scale.days):
            d = scale.origin + timedelta(days=i)
            bottom.append(
                Tick(
                    scale.x(d),
                    scale.px_per_day,
                    f"{WEEKDAYS[d.weekday()]} {d.day}",
                    strong=d.weekday() == 0,
                )
            )
        return top, bottom
    if zoom == "week":
        top = _month_ticks(scale)
        bottom = []
        d = scale.origin - timedelta(days=scale.origin.weekday())
        while d < scale.end:
            x0 = max(0.0, scale.x(d))
            bottom.append(Tick(x0, 7 * scale.px_per_day, d.strftime("%d.%m."), strong=True))
            d += timedelta(days=7)
        return top, bottom
    # month
    top = []
    year = scale.origin.year
    while date(year, 1, 1) < scale.end:
        x0 = max(0.0, scale.x(date(year, 1, 1)))
        x1 = min(scale.width, scale.x(date(year + 1, 1, 1)))
        top.append(Tick(x0, x1 - x0, str(year), strong=True))
        year += 1
    return top, _month_ticks(scale, short=True, with_year=False)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def duration_days(start: date, end: date) -> int:
    return (end - start).days + 1


def describe_span(start: date, end: date) -> str:
    n = duration_days(start, end)
    days = "dan" if n % 10 == 1 and n % 100 != 11 else "dana"
    return f"{start.strftime('%d.%m.')} – {end.strftime('%d.%m.%Y.')}  ({n} {days})"
