"""Podrazumevana podešavanja i kategorije budžeta koje postoje u svakoj novoj bazi."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BudgetCategory, Setting

DEFAULT_SETTINGS: dict[str, str] = {
    "user_name": "",
    "base_currency": "RSD",
    "theme": "system",  # system / light / dark
    "language": "sr",
    "default_hourly_rate_minor": "0",
    "budget_warn_percent": "80",
}

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Rad", "#2F55D4"),
    ("Materijal", "#0E7C86"),
    ("Softver i licence", "#7A5AC0"),
    ("Putni troškovi", "#B8620A"),
    ("Ostalo", "#7C7C86"),
]


def ensure_defaults(session: Session) -> None:
    """Dodaje samo ono što nedostaje; postojeće vrednosti korisnika se ne diraju."""
    existing = set(session.scalars(select(Setting.key)))
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing:
            session.add(Setting(key=key, value=value))

    if session.scalar(select(BudgetCategory.id).limit(1)) is None:
        for order, (name, color) in enumerate(DEFAULT_CATEGORIES):
            session.add(BudgetCategory(name=name, color=color, sort_order=order))
    session.flush()


def get_setting(session: Session, key: str) -> str:
    row = session.get(Setting, key)
    if row is not None:
        return row.value
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
