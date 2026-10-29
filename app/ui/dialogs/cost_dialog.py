"""Dijalog za trošak ili prihod (iznos u RSD/EUR/USD sa kursom na dan unosa)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
)

from app.db.models import CostEntry, IncomeEntry
from app.services import budget as budget_service
from app.services import tasks as task_service
from app.services.money import SUPPORTED_CURRENCIES, format_money, to_base_minor
from app.ui.context import AppContext
from app.ui.dialogs.base import FormDialog
from app.ui.widgets.fields import MoneyEdit, date_edit, from_qdate


class MoneyEntryDialog(FormDialog):
    def __init__(
        self,
        ctx: AppContext,
        kind: str = "cost",
        entry_id: str | None = None,
        parent=None,
        task_id: str | None = None,
    ) -> None:
        self.kind = kind
        title = {
            ("cost", False): "Novi trošak",
            ("cost", True): "Izmena troška",
            ("income", False): "Novi prihod",
            ("income", True): "Izmena prihoda",
        }
        super().__init__(title[(kind, bool(entry_id))], parent)
        self.ctx = ctx
        self.entry_id = entry_id
        model = CostEntry if kind == "cost" else IncomeEntry

        with ctx.session() as s:
            self.base = budget_service.base_currency(s)
            entry = s.get(model, entry_id) if entry_id else None
            cats = [(c.id, c.name) for c in budget_service.categories(s)]
            tasks = [
                (t.id, ("    " * d) + t.title) for t, d in task_service.tree(s, ctx.project_id)
            ]
            rates = {c: budget_service.last_rate(s, c) for c in SUPPORTED_CURRENCIES}

        self.rates = rates
        self.day = date_edit(entry.date if entry else date.today())
        self.amount = MoneyEdit(entry.amount_minor if entry else 0)
        self.currency = QComboBox()
        for c in SUPPORTED_CURRENCIES:
            self.currency.addItem(c, c)
        self.currency.setCurrentIndex(
            max(0, self.currency.findData(entry.currency if entry else self.base))
        )
        self.rate = QDoubleSpinBox()
        self.rate.setDecimals(4)
        self.rate.setRange(0, 1_000_000)
        self.rate.setValue(float(entry.exchange_rate) if entry else 1.0)
        self.rate_label = QLabel(f"{self.base} za 1")
        self.converted = QLabel()
        self.converted.setProperty("muted", True)

        amount_row = QHBoxLayout()
        amount_row.setSpacing(8)
        amount_row.addWidget(self.amount, 2)
        amount_row.addWidget(self.currency)
        rate_row = QHBoxLayout()
        rate_row.setSpacing(8)
        rate_row.addWidget(self.rate, 1)
        rate_row.addWidget(self.rate_label)
        rate_row.addWidget(self.converted, 2)

        self.form.addRow("Datum", self.day)
        self.form.addRow("Iznos", amount_row)
        self.form.addRow("Kurs", rate_row)

        if kind == "cost":
            self.category = QComboBox()
            for cid, name in cats:
                self.category.addItem(name, cid)
            if entry:
                self.category.setCurrentIndex(max(0, self.category.findData(entry.category_id)))
            self.task = QComboBox()
            self.task.addItem("Bez zadatka", None)
            for tid, name in tasks:
                self.task.addItem(name, tid)
            wanted = entry.task_id if entry else task_id
            if wanted:
                self.task.setCurrentIndex(max(0, self.task.findData(wanted)))
            self.vendor = QLineEdit(entry.vendor if entry else "")
            self.vendor.setPlaceholderText("npr. Figma, štamparija, sopstveni rad")
            self.note = QPlainTextEdit(entry.note if entry else "")
            self.note.setFixedHeight(70)
            self.form.addRow("Kategorija", self.category)
            self.form.addRow("Zadatak", self.task)
            self.form.addRow("Dobavljač", self.vendor)
            self.form.addRow("Napomena", self.note)
        else:
            self.description = QLineEdit(entry.description if entry else "")
            self.description.setPlaceholderText("npr. Avans 50%, završna rata")
            self.form.addRow("Opis", self.description)

        self.currency.currentIndexChanged.connect(self._currency_changed)
        self.rate.valueChanged.connect(lambda _v: self._update_converted())
        self.amount.textChanged.connect(lambda _t: self._update_converted())
        self._currency_changed(initial=bool(entry))
        self.amount.setFocus()

    def _currency_changed(self, _i=None, initial: bool = False) -> None:
        cur = self.currency.currentData()
        foreign = cur != self.base
        self.rate.setEnabled(foreign)
        self.rate_label.setText(f"{self.base} za 1 {cur}" if foreign else "osnovna valuta")
        if not foreign:
            self.rate.setValue(1.0)
        elif not initial:
            last = self.rates.get(cur)
            self.rate.setValue(float(last) if last else 0.0)
        self._update_converted()

    def _update_converted(self) -> None:
        cur = self.currency.currentData()
        if cur == self.base or not self.amount.is_valid():
            self.converted.setText("")
            return
        base = to_base_minor(self.amount.value_minor(), Decimal(str(self.rate.value())))
        self.converted.setText(f"= {format_money(base, self.base)}")

    def validate(self) -> None:
        if not self.amount.is_valid():
            raise ValueError("Iznos nije ispravan.")
        if self.amount.value_minor() <= 0:
            raise ValueError("Unesi iznos.")
        if self.currency.currentData() != self.base and self.rate.value() <= 0:
            raise ValueError(
                f"Unesi kurs: koliko {self.base} vredi 1 {self.currency.currentData()}."
            )
        if self.kind == "cost" and not self.category.currentData():
            raise ValueError("Izaberi kategoriju.")

    def save(self) -> bool:
        pid = self.ctx.project_id
        common = {
            "on": from_qdate(self.day.date()),
            "amount_minor": self.amount.value_minor(),
            "currency": self.currency.currentData(),
            "rate": Decimal(str(round(self.rate.value(), 4))),
        }

        def work(s):
            if self.kind == "cost":
                extra = {
                    "category_id": self.category.currentData(),
                    "task_id": self.task.currentData(),
                    "vendor": self.vendor.text(),
                    "note": self.note.toPlainText(),
                }
                if self.entry_id:
                    budget_service.update_cost(
                        s, s.get(CostEntry, self.entry_id), **common, **extra
                    )
                else:
                    budget_service.add_cost(s, pid, **common, **extra)
            else:
                desc = self.description.text()
                if self.entry_id:
                    budget_service.update_income(
                        s, s.get(IncomeEntry, self.entry_id), **common, description=desc
                    )
                else:
                    budget_service.add_income(s, pid, **common, description=desc)
            return True

        return bool(self.ctx.run(work, self))


def edit_money_entry(
    ctx: AppContext, kind: str, entry_id: str | None = None, parent=None, task_id: str | None = None
) -> bool:
    dlg = MoneyEntryDialog(ctx, kind, entry_id, parent, task_id)
    if dlg.exec() == dlg.DialogCode.Accepted:
        return dlg.save()
    return False
