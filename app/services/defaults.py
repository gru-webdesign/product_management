"""Podrazumevana podešavanja i kategorije budžeta koje postoje u svakoj novoj bazi."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BudgetCategory, Setting

DEFAULT_SETTINGS: dict[str, str] = {
    "user_name": "",
    "base_currency": "RSD",
    "theme": "dark",  # system / light / dark
    "language": "sr",
    "default_hourly_rate_minor": "0",
    "budget_warn_percent": "80",
}

DEFAULT_CATEGORIES: list[tuple[str, str]] = [
    ("Interni rad", "#2F55D4"),
    ("Spoljni saradnici i konsultanti", "#0E7C86"),
    ("Razvoj kod dobavljača", "#22844C"),
    ("Softver i licence", "#7A5AC0"),
    ("Infrastruktura i hosting", "#5E5E68"),
    ("Pravne usluge", "#8A7A12"),
    ("Revizija i sertifikacija", "#BE3455"),
    ("Bezbednost i testiranje", "#C2410C"),
    ("Marketing", "#B8620A"),
    ("Obuke", "#4F7CC2"),
    ("Materijal i oprema", "#6B8E4E"),
    ("Putni troškovi", "#A0522D"),
    ("Ostalo", "#7C7C86"),
]

# Kategorije iz prve verzije: baza koja ima tačno njih dobija novi spisak (preimenovanje
# zadržava sve troškove i planove vezane za kategoriju).
OLD_CATEGORIES = ["Rad", "Materijal", "Softver i licence", "Putni troškovi", "Ostalo"]
OLD_RENAMES = {"Rad": "Interni rad", "Materijal": "Materijal i oprema"}


def ensure_defaults(session: Session) -> None:
    """Dodaje samo ono što nedostaje; postojeće vrednosti korisnika se ne diraju."""
    existing = set(session.scalars(select(Setting.key)))
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing:
            session.add(Setting(key=key, value=value))

    categories = list(session.scalars(select(BudgetCategory)))
    if not categories:
        for order, (name, color) in enumerate(DEFAULT_CATEGORIES):
            session.add(BudgetCategory(name=name, color=color, sort_order=order))
    elif sorted(c.name for c in categories) == sorted(OLD_CATEGORIES):
        _upgrade_old_categories(session, categories)
    session.flush()


def _upgrade_old_categories(session: Session, categories: list[BudgetCategory]) -> None:
    by_name = {c.name: c for c in categories}
    for old, new in OLD_RENAMES.items():
        by_name[old].name = new
    by_name = {c.name: c for c in categories}
    for order, (name, color) in enumerate(DEFAULT_CATEGORIES):
        if name in by_name:
            by_name[name].sort_order = order
        else:
            session.add(BudgetCategory(name=name, color=color, sort_order=order))


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
