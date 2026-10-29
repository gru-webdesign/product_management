"""Budžet projekta: kategorije, planirani iznosi, troškovi, prihodi, pregled i upozorenja.

Svi zbirovi su u osnovnoj valuti (podešavanje base_currency, podrazumevano RSD), po kursu
koji je unet uz svaki trošak/prihod.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Budget, BudgetCategory, CostEntry, IncomeEntry, Task
from app.services import activity
from app.services.defaults import get_setting, set_setting
from app.services.money import SUPPORTED_CURRENCIES, format_money, to_base_minor

# --- kategorije ----------------------------------------------------------------------------------


def categories(session: Session) -> list[BudgetCategory]:
    return list(
        session.scalars(
            select(BudgetCategory).order_by(BudgetCategory.sort_order, BudgetCategory.name)
        )
    )


def create_category(session: Session, name: str, color: str = "#8B8D98") -> BudgetCategory:
    name = name.strip()
    if not name:
        raise ValueError("Naziv kategorije je obavezan.")
    if session.scalar(
        select(BudgetCategory.id).where(func.lower(BudgetCategory.name) == name.lower())
    ):
        raise ValueError(f"Kategorija „{name}“ već postoji.")
    order = (session.scalar(select(func.max(BudgetCategory.sort_order))) or 0) + 1
    cat = BudgetCategory(name=name, color=color, sort_order=order)
    session.add(cat)
    session.flush()
    return cat


def rename_category(session: Session, cat: BudgetCategory, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Naziv kategorije je obavezan.")
    other = session.scalar(
        select(BudgetCategory.id).where(
            func.lower(BudgetCategory.name) == name.lower(), BudgetCategory.id != cat.id
        )
    )
    if other:
        raise ValueError(f"Kategorija „{name}“ već postoji.")
    cat.name = name
    session.flush()


def delete_category(session: Session, cat: BudgetCategory) -> None:
    used = session.scalar(select(func.count(CostEntry.id)).where(CostEntry.category_id == cat.id))
    if used:
        raise ValueError(f"Kategorija „{cat.name}“ ima {used} troškova i ne može da se obriše.")
    for b in session.scalars(select(Budget).where(Budget.category_id == cat.id)):
        session.delete(b)
    session.delete(cat)
    session.flush()


# --- planirani budžet ----------------------------------------------------------------------------


def planned(session: Session, project_id: str) -> dict[str, int]:
    rows = session.execute(
        select(Budget.category_id, Budget.planned_minor).where(Budget.project_id == project_id)
    ).all()
    return {cid: amount for cid, amount in rows}


def set_planned(session: Session, project_id: str, category_id: str, amount_minor: int) -> None:
    if amount_minor < 0:
        raise ValueError("Planirani iznos ne može biti negativan.")
    row = session.scalar(
        select(Budget).where(Budget.project_id == project_id, Budget.category_id == category_id)
    )
    old = row.planned_minor if row else 0
    if old == amount_minor:
        return
    if row is None:
        session.add(
            Budget(project_id=project_id, category_id=category_id, planned_minor=amount_minor)
        )
    else:
        row.planned_minor = amount_minor
    cat = session.get(BudgetCategory, category_id)
    activity.log(
        session,
        "budget",
        project_id,
        "update",
        project_id,
        f"budžet: {cat.name if cat else ''}",
        format_money(old),
        format_money(amount_minor),
    )
    session.flush()


# --- troškovi i prihodi --------------------------------------------------------------------------


def _rate(currency: str, rate, base: str) -> Decimal:
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Valuta {currency} nije podržana.")
    if currency == base:
        return Decimal("1")
    try:
        value = Decimal(str(rate))
    except InvalidOperation as exc:
        raise ValueError("Kurs nije ispravan broj.") from exc
    if value <= 0:
        raise ValueError(f"Unesi kurs za {currency} (koliko {base} vredi 1 {currency}).")
    return value


def base_currency(session: Session) -> str:
    return get_setting(session, "base_currency") or "RSD"


def last_rate(session: Session, currency: str) -> Decimal | None:
    value = get_setting(session, f"last_rate_{currency}")
    try:
        return Decimal(value) if value else None
    except InvalidOperation:
        return None


def _money_fields(session: Session, amount_minor: int, currency: str, rate) -> dict:
    if amount_minor is None or amount_minor < 0:
        raise ValueError("Iznos ne može biti negativan.")
    if amount_minor == 0:
        raise ValueError("Unesi iznos.")
    base = base_currency(session)
    r = _rate(currency, rate, base)
    if currency != base:
        set_setting(session, f"last_rate_{currency}", str(r))
    return {
        "amount_minor": amount_minor,
        "currency": currency,
        "exchange_rate": r,
        "amount_base_minor": to_base_minor(amount_minor, r),
    }


def add_cost(
    session: Session,
    project_id: str,
    *,
    on: date,
    amount_minor: int,
    category_id: str,
    currency: str = "RSD",
    rate=1,
    task_id: str | None = None,
    vendor: str = "",
    note: str = "",
) -> CostEntry:
    if not session.get(BudgetCategory, category_id):
        raise ValueError("Izaberi kategoriju.")
    if task_id:
        task = session.get(Task, task_id)
        if task is None or task.project_id != project_id:
            raise ValueError("Zadatak mora biti iz istog projekta.")
    entry = CostEntry(
        project_id=project_id,
        date=on,
        category_id=category_id,
        task_id=task_id,
        vendor=vendor.strip(),
        note=note.strip(),
        **_money_fields(session, amount_minor, currency, rate),
    )
    session.add(entry)
    session.flush()
    activity.log(
        session,
        "cost",
        entry.id,
        "create",
        project_id,
        "iznos",
        None,
        format_money(entry.amount_minor, entry.currency),
    )
    return entry


def update_cost(
    session: Session,
    entry: CostEntry,
    *,
    on: date,
    amount_minor: int,
    category_id: str,
    currency: str,
    rate=1,
    task_id: str | None = None,
    vendor: str = "",
    note: str = "",
) -> None:
    if not session.get(BudgetCategory, category_id):
        raise ValueError("Izaberi kategoriju.")
    fields = _money_fields(session, amount_minor, currency, rate)
    old = format_money(entry.amount_minor, entry.currency)
    entry.date, entry.category_id, entry.task_id = on, category_id, task_id
    entry.vendor, entry.note = vendor.strip(), note.strip()
    for k, v in fields.items():
        setattr(entry, k, v)
    activity.log(
        session,
        "cost",
        entry.id,
        "update",
        entry.project_id,
        "iznos",
        old,
        format_money(entry.amount_minor, entry.currency),
    )
    session.flush()


def delete_cost(session: Session, entry: CostEntry) -> None:
    activity.log(
        session,
        "cost",
        entry.id,
        "delete",
        entry.project_id,
        "iznos",
        format_money(entry.amount_minor, entry.currency),
        None,
    )
    session.delete(entry)
    session.flush()


def add_income(
    session: Session,
    project_id: str,
    *,
    on: date,
    amount_minor: int,
    currency: str = "RSD",
    rate=1,
    description: str = "",
) -> IncomeEntry:
    entry = IncomeEntry(
        project_id=project_id,
        date=on,
        description=description.strip(),
        **_money_fields(session, amount_minor, currency, rate),
    )
    session.add(entry)
    session.flush()
    return entry


def update_income(
    session: Session,
    entry: IncomeEntry,
    *,
    on: date,
    amount_minor: int,
    currency: str,
    rate=1,
    description: str = "",
) -> None:
    fields = _money_fields(session, amount_minor, currency, rate)
    entry.date, entry.description = on, description.strip()
    for k, v in fields.items():
        setattr(entry, k, v)
    session.flush()


def delete_income(session: Session, entry: IncomeEntry) -> None:
    session.delete(entry)
    session.flush()


def costs(session: Session, project_id: str) -> list[CostEntry]:
    return list(
        session.scalars(
            select(CostEntry)
            .where(CostEntry.project_id == project_id)
            .order_by(CostEntry.date.desc(), CostEntry.created_at.desc())
        )
    )


def incomes(session: Session, project_id: str) -> list[IncomeEntry]:
    return list(
        session.scalars(
            select(IncomeEntry)
            .where(IncomeEntry.project_id == project_id)
            .order_by(IncomeEntry.date.desc(), IncomeEntry.created_at.desc())
        )
    )


# --- pregled -------------------------------------------------------------------------------------


def state_for(spent: int, plan: int, warn_percent: int) -> str:
    if plan <= 0:
        return "unplanned" if spent > 0 else "ok"
    if spent > plan:
        return "over"
    if spent * 100 >= plan * warn_percent:
        return "warn"
    return "ok"


@dataclass
class CategoryLine:
    category_id: str
    name: str
    color: str
    planned: int
    spent: int

    @property
    def remaining(self) -> int:
        return self.planned - self.spent

    @property
    def percent(self) -> int:
        return (
            round(self.spent * 100 / self.planned) if self.planned else (100 if self.spent else 0)
        )


@dataclass
class Summary:
    base: str
    warn_percent: int
    lines: list[CategoryLine] = field(default_factory=list)
    income: int = 0
    tasks_planned: int = 0
    hours_actual: float = 0.0
    hourly_rate: int = 0

    @property
    def planned(self) -> int:
        return sum(line.planned for line in self.lines)

    @property
    def spent(self) -> int:
        return sum(line.spent for line in self.lines)

    @property
    def remaining(self) -> int:
        return self.planned - self.spent

    @property
    def percent(self) -> int:
        return round(self.spent * 100 / self.planned) if self.planned else 0

    @property
    def profit(self) -> int:
        return self.income - self.spent

    @property
    def labor_value(self) -> int:
        return round(self.hours_actual * self.hourly_rate)

    @property
    def state(self) -> str:
        return state_for(self.spent, self.planned, self.warn_percent)

    def line_state(self, line: CategoryLine) -> str:
        return state_for(line.spent, line.planned, self.warn_percent)

    def warnings(self) -> list[tuple[str, str]]:
        """(nivo, poruka) — nivo je 'warn' ili 'over'."""
        out: list[tuple[str, str]] = []
        fm = lambda v: format_money(v, self.base)  # noqa: E731
        if self.state == "over":
            out.append(
                (
                    "over",
                    f"Budžet projekta je prekoračen za {fm(-self.remaining)} "
                    f"({self.percent}% potrošeno).",
                )
            )
        elif self.state == "warn":
            out.append(
                (
                    "warn",
                    f"Potrošeno je {self.percent}% budžeta projekta — ostalo {fm(self.remaining)}.",
                )
            )
        for line in self.lines:
            st = self.line_state(line)
            if st == "over":
                out.append(("over", f"„{line.name}“: prekoračeno za {fm(-line.remaining)}."))
            elif st == "warn":
                out.append(("warn", f"„{line.name}“: potrošeno {line.percent}% planiranog."))
            elif st == "unplanned":
                out.append(
                    ("warn", f"„{line.name}“: {fm(line.spent)} troška bez planiranog budžeta.")
                )
        if self.planned and self.tasks_planned > self.planned:
            out.append(
                (
                    "warn",
                    f"Planirani troškovi zadataka ({fm(self.tasks_planned)}) su veći "
                    f"od budžeta ({fm(self.planned)}).",
                )
            )
        return out


def summary(session: Session, project_id: str) -> Summary:
    warn = int(get_setting(session, "budget_warn_percent") or 80)
    s = Summary(base=base_currency(session), warn_percent=warn)
    plan = planned(session, project_id)
    spent_rows = session.execute(
        select(CostEntry.category_id, func.sum(CostEntry.amount_base_minor))
        .where(CostEntry.project_id == project_id)
        .group_by(CostEntry.category_id)
    ).all()
    spent = {cid: int(total or 0) for cid, total in spent_rows}
    for cat in categories(session):
        if cat.id in plan or cat.id in spent:
            s.lines.append(
                CategoryLine(cat.id, cat.name, cat.color, plan.get(cat.id, 0), spent.get(cat.id, 0))
            )
    s.income = int(
        session.scalar(
            select(func.sum(IncomeEntry.amount_base_minor)).where(
                IncomeEntry.project_id == project_id
            )
        )
        or 0
    )
    s.tasks_planned = int(
        session.scalar(
            select(func.sum(Task.planned_cost_minor)).where(Task.project_id == project_id)
        )
        or 0
    )
    s.hours_actual = float(
        session.scalar(select(func.sum(Task.actual_hours)).where(Task.project_id == project_id))
        or 0
    )
    s.hourly_rate = int(get_setting(session, "default_hourly_rate_minor") or 0)
    return s


def spending_series(session: Session, project_id: str) -> list[tuple[date, int]]:
    """Kumulativna potrošnja po danima (za grafikon)."""
    rows = session.execute(
        select(CostEntry.date, func.sum(CostEntry.amount_base_minor))
        .where(CostEntry.project_id == project_id)
        .group_by(CostEntry.date)
        .order_by(CostEntry.date)
    ).all()
    total, out = 0, []
    for day, amount in rows:
        total += int(amount or 0)
        out.append((day, total))
    return out
