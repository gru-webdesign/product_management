"""Dijalozi za stavke registra: rizik ili problem, zainteresovana strana, dokument, odluka."""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
)

from app import labels
from app.db.models import DecisionStatus, DocStatus, RiskKind, RiskStatus
from app.ui.dialogs.base import FormDialog
from app.ui.widgets.fields import OptionalDateField, SuggestCombo


def _combo(items: dict, current) -> QComboBox:
    combo = QComboBox()
    for value, label in items.items():
        combo.addItem(label, value)
    idx = combo.findData(current)
    combo.setCurrentIndex(max(0, idx))
    return combo


def _text(value: str = "", placeholder: str = "", height: int = 70) -> QPlainTextEdit:
    edit = QPlainTextEdit(value or "")
    edit.setPlaceholderText(placeholder)
    edit.setFixedHeight(height)
    return edit


def _task_combo(tasks: list[tuple[str, str]], current: str | None) -> QComboBox:
    combo = QComboBox()
    combo.addItem("Nije vezano za zadatak", None)
    for tid, title in tasks:
        combo.addItem(title, tid)
    idx = combo.findData(current) if current else 0
    combo.setCurrentIndex(max(0, idx))
    combo.setMaxVisibleItems(16)
    return combo


class RegistryDialog(FormDialog):
    """Zajednička osnova: obj=None znači nova stavka; values() vraća polja za servis."""

    title_new = ""
    title_edit = ""

    def __init__(
        self,
        obj: Any | None,
        tasks: list[tuple[str, str]],
        suggest: dict[str, list[str]],
        parent=None,
    ) -> None:
        super().__init__(self.title_edit if obj is not None else self.title_new, parent)
        self.setMinimumWidth(560)
        self.obj = obj
        self.tasks = tasks
        self.suggest = suggest
        self.build(obj)

    def get(self, field: str, default=None):
        return getattr(self.obj, field) if self.obj is not None else default

    def build(self, obj) -> None:  # pragma: no cover - podklase
        raise NotImplementedError

    def values(self) -> dict[str, Any]:  # pragma: no cover - podklase
        raise NotImplementedError


class RiskDialog(RegistryDialog):
    title_new = "Novi rizik ili problem"
    title_edit = "Rizik ili problem"

    def build(self, obj) -> None:
        self.kind = _combo(labels.RISK_KIND, self.get("kind", RiskKind.RISK))
        self.title_field = QLineEdit(self.get("title", ""))
        self.title_field.setPlaceholderText("npr. Partner kasni sa dostavom API dokumentacije")
        self.probability = _combo(labels.PROBABILITY, self.get("probability", 2))
        self.impact = _combo(labels.IMPACT, self.get("impact", 2))
        self.score = QLabel()
        self.score.setProperty("muted", True)
        for c in (self.probability, self.impact):
            c.currentIndexChanged.connect(lambda _i: self._update_score())
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.probability, 1)
        row.addSpacing(10)
        row.addWidget(QLabel("Uticaj"))
        row.addWidget(self.impact, 1)
        self.status = _combo(labels.RISK_STATUS, self.get("status", RiskStatus.OPEN))
        self.owner = SuggestCombo(self.suggest.get("people", []), self.get("owner", ""))
        self.due = OptionalDateField(self.get("due_date"), "Postavi")
        self.description = _text(
            self.get("description", ""), "Šta može da se desi (ili šta se desilo) i zašto"
        )
        self.mitigation = _text(
            self.get("mitigation", ""),
            "Mera: kako se smanjuje verovatnoća ili uticaj, plan B, ko šta radi",
        )
        self.task = _task_combo(self.tasks, self.get("task_id"))

        self.form.addRow("Vrsta", self.kind)
        self.form.addRow("Naziv", self.title_field)
        self.form.addRow("Verovatnoća", row)
        self.form.addRow("Ocena", self.score)
        self.form.addRow("Status", self.status)
        self.form.addRow("Nosilac", self.owner)
        self.form.addRow("Rok za meru", self.due)
        self.form.addRow("Opis", self.description)
        self.form.addRow("Mera", self.mitigation)
        self.form.addRow("Zadatak", self.task)
        self._update_score()
        self.title_field.setFocus()

    def _update_score(self) -> None:
        score = self.probability.currentData() * self.impact.currentData()
        self.score.setText(f"{labels.risk_level(score)} ({score} od 16)")

    def validate(self) -> None:
        if not self.title_field.text().strip():
            raise ValueError("Unesi naziv rizika ili problema.")

    def values(self) -> dict[str, Any]:
        return {
            "kind": self.kind.currentData(),
            "title": self.title_field.text(),
            "probability": self.probability.currentData(),
            "impact": self.impact.currentData(),
            "status": self.status.currentData(),
            "owner": self.owner.value(),
            "due_date": self.due.value(),
            "description": self.description.toPlainText(),
            "mitigation": self.mitigation.toPlainText(),
            "task_id": self.task.currentData(),
        }


class StakeholderDialog(RegistryDialog):
    title_new = "Nova zainteresovana strana"
    title_edit = "Zainteresovana strana"

    def build(self, obj) -> None:
        self.name = QLineEdit(self.get("name", ""))
        self.name.setPlaceholderText("Ime i prezime ili naziv tima")
        self.organization = SuggestCombo(
            self.suggest.get("organization", labels.ORGANIZATIONS), self.get("organization", "")
        )
        self.role = SuggestCombo(self.suggest.get("people", []), self.get("role", ""))
        self.role.lineEdit().setPlaceholderText("npr. Compliance, IT razvoj, vlasnik proizvoda")
        self.raci = _combo(labels.RACI, self.get("raci", "I"))
        self.influence = _combo(labels.LEVEL3, self.get("influence", 2))
        self.interest = _combo(labels.LEVEL3, self.get("interest", 2))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.influence, 1)
        row.addSpacing(10)
        row.addWidget(QLabel("Interes"))
        row.addWidget(self.interest, 1)
        self.email = QLineEdit(self.get("email", ""))
        self.phone = QLineEdit(self.get("phone", ""))
        self.notes = _text(self.get("notes", ""), "Očekivanja, kako i koliko često informisati")

        self.form.addRow("Ime / tim", self.name)
        self.form.addRow("Organizacija", self.organization)
        self.form.addRow("Uloga / funkcija", self.role)
        self.form.addRow("RACI", self.raci)
        self.form.addRow("Uticaj", row)
        self.form.addRow("E-pošta", self.email)
        self.form.addRow("Telefon", self.phone)
        self.form.addRow("Napomene", self.notes)
        self.name.setFocus()

    def validate(self) -> None:
        if not self.name.text().strip():
            raise ValueError("Unesi ime osobe ili naziv tima.")

    def values(self) -> dict[str, Any]:
        return {
            "name": self.name.text(),
            "organization": self.organization.value(),
            "role": self.role.value(),
            "raci": self.raci.currentData(),
            "influence": self.influence.currentData(),
            "interest": self.interest.currentData(),
            "email": self.email.text().strip(),
            "phone": self.phone.text().strip(),
            "notes": self.notes.toPlainText(),
        }


class DocumentDialog(RegistryDialog):
    title_new = "Novi dokument ili link"
    title_edit = "Dokument"

    def build(self, obj) -> None:
        self.title_field = QLineEdit(self.get("title", ""))
        self.title_field.setPlaceholderText("npr. Specifikacija integracije sa partnerom")
        self.kind = SuggestCombo(
            self.suggest.get("doc_kind", labels.DOC_KINDS), self.get("kind", "")
        )
        self.location = QLineEdit(self.get("location", ""))
        self.location.setPlaceholderText("Link (SharePoint, Confluence…) ili putanja do fajla")
        browse = QPushButton("Izaberi fajl…")
        browse.clicked.connect(self._browse)
        loc = QHBoxLayout()
        loc.setSpacing(8)
        loc.addWidget(self.location, 1)
        loc.addWidget(browse)
        self.version = QLineEdit(self.get("version", ""))
        self.version.setPlaceholderText("npr. 1.2")
        self.status = _combo(labels.DOC_STATUS, self.get("status", DocStatus.DRAFT))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.version, 1)
        row.addSpacing(10)
        row.addWidget(QLabel("Status"))
        row.addWidget(self.status, 1)
        self.owner = SuggestCombo(self.suggest.get("people", []), self.get("owner", ""))
        self.doc_date = OptionalDateField(self.get("doc_date"), "Postavi")
        self.task = _task_combo(self.tasks, self.get("task_id"))
        self.notes = _text(self.get("notes", ""), "Šta sadrži, ko treba da odobri, napomene")

        self.form.addRow("Naziv", self.title_field)
        self.form.addRow("Vrsta", self.kind)
        self.form.addRow("Lokacija", loc)
        self.form.addRow("Verzija", row)
        self.form.addRow("Nosilac", self.owner)
        self.form.addRow("Datum", self.doc_date)
        self.form.addRow("Zadatak", self.task)
        self.form.addRow("Napomene", self.notes)
        hint = QLabel("Etapa čuva samo link ili putanju; sam fajl ostaje gde jeste.")
        hint.setProperty("faint", True)
        self.form.addRow("", hint)
        self.title_field.setFocus()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Izaberi dokument")
        if path:
            self.location.setText(path)
            if not self.title_field.text().strip():
                from pathlib import Path

                self.title_field.setText(Path(path).stem)

    def validate(self) -> None:
        if not self.title_field.text().strip():
            raise ValueError("Unesi naziv dokumenta.")

    def values(self) -> dict[str, Any]:
        return {
            "title": self.title_field.text(),
            "kind": self.kind.value(),
            "location": self.location.text().strip(),
            "version": self.version.text().strip(),
            "status": self.status.currentData(),
            "owner": self.owner.value(),
            "doc_date": self.doc_date.value(),
            "task_id": self.task.currentData(),
            "notes": self.notes.toPlainText(),
        }


class DecisionDialog(RegistryDialog):
    title_new = "Nova odluka"
    title_edit = "Odluka"

    def build(self, obj) -> None:
        from PySide6.QtWidgets import QDateEdit

        from app.ui.widgets.fields import from_qdate, to_qdate

        self._from_qdate = from_qdate
        self.decided_on = QDateEdit(to_qdate(self.get("decided_on", date.today())))
        self.decided_on.setCalendarPopup(True)
        self.decided_on.setDisplayFormat("dd.MM.yyyy.")
        self.title_field = QLineEdit(self.get("title", ""))
        self.title_field.setPlaceholderText("npr. Integracija preko REST API-ja umesto fajlova")
        self.status = _combo(labels.DECISION_STATUS, self.get("status", DecisionStatus.APPROVED))
        self.approved_by = SuggestCombo(self.suggest.get("people", []), self.get("approved_by", ""))
        self.approved_by.lineEdit().setPlaceholderText("ko je odobrio (osoba, odbor, uprava)")
        self.decision = _text(self.get("decision", ""), "Šta je tačno odlučeno", 80)
        self.rationale = _text(
            self.get("rationale", ""), "Zašto: razlozi, razmotrene opcije, posledice", 80
        )
        self.task = _task_combo(self.tasks, self.get("task_id"))

        self.form.addRow("Datum", self.decided_on)
        self.form.addRow("Naziv", self.title_field)
        self.form.addRow("Status", self.status)
        self.form.addRow("Odobrio", self.approved_by)
        self.form.addRow("Odluka", self.decision)
        self.form.addRow("Obrazloženje", self.rationale)
        self.form.addRow("Zadatak", self.task)
        self.title_field.setFocus()

    def validate(self) -> None:
        if not self.title_field.text().strip():
            raise ValueError("Unesi kratak naziv odluke.")

    def values(self) -> dict[str, Any]:
        return {
            "decided_on": self._from_qdate(self.decided_on.date()),
            "title": self.title_field.text(),
            "status": self.status.currentData(),
            "approved_by": self.approved_by.value(),
            "decision": self.decision.toPlainText(),
            "rationale": self.rationale.toPlainText(),
            "task_id": self.task.currentData(),
        }
