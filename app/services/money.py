"""Rad sa novcem: iznosi se čuvaju kao celi brojevi u najmanjoj jedinici (1 RSD = 100 para)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

SUPPORTED_CURRENCIES = ("RSD", "EUR", "USD")


def to_minor(amount: Decimal | int | float | str) -> int:
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(value * 100)


def from_minor(minor: int) -> Decimal:
    return (Decimal(minor) / 100).quantize(Decimal("0.01"))


def to_base_minor(amount_minor: int, rate: Decimal | int | str) -> int:
    """Preračun u osnovnu valutu po kursu (npr. 1 EUR = 117.2 RSD)."""
    value = Decimal(amount_minor) * Decimal(str(rate))
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(minor: int, currency: str = "RSD") -> str:
    """Srpski format: 1.234.567,89 RSD."""
    value = from_minor(minor)
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{sign}{'.'.join(groups)},{frac} {currency}"
