"""Dijalog za novi projekat ili izmenu postojećeg."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit

from app.db.models import Project, ProjectStatus
from app.labels import PROJECT_COLORS, PROJECT_STATUS
from app.ui.dialogs.base import FormDialog
from app.ui.widgets.fields import ColorPicker, OptionalDateField


class ProjectDialog(FormDialog):
    def __init__(self, project: Project | None = None, parent=None) -> None:
        super().__init__("Izmena projekta" if project else "Novi projekat", parent)

        self.name = QLineEdit(project.name if project else "")
        self.name.setPlaceholderText("npr. Redizajn sajta za piceriju")
        self.client = QLineEdit(project.client if project else "")
        self.client.setPlaceholderText("opciono")
        self.color = ColorPicker(PROJECT_COLORS, project.color if project else None)
        self.status = QComboBox()
        for status, label in PROJECT_STATUS.items():
            self.status.addItem(label, status)
        self.status.setCurrentIndex(
            list(PROJECT_STATUS).index(project.status if project else ProjectStatus.ACTIVE)
        )
        self.start = OptionalDateField(project.start_date if project else None, "Postavi")
        self.end = OptionalDateField(project.end_date if project else None, "Postavi")
        self.description = QPlainTextEdit(project.description if project else "")
        self.description.setPlaceholderText("Cilj projekta, napomene…")
        self.description.setFixedHeight(90)

        self.form.addRow("Naziv", self.name)
        self.form.addRow("Klijent", self.client)
        self.form.addRow("Boja", self.color)
        self.form.addRow("Status", self.status)
        self.form.addRow("Početak", self.start)
        self.form.addRow("Kraj", self.end)
        self.form.addRow("Opis", self.description)
        self.name.setFocus()

    def validate(self) -> None:
        if not self.name.text().strip():
            raise ValueError("Unesi naziv projekta.")
        start, end = self.start.value(), self.end.value()
        if start and end and start > end:
            raise ValueError("Početak mora biti pre kraja.")

    def values(self) -> dict[str, Any]:
        return {
            "name": self.name.text().strip(),
            "client": self.client.text().strip(),
            "color": self.color.value(),
            "status": self.status.currentData(),
            "start_date": self.start.value(),
            "end_date": self.end.value(),
            "description": self.description.toPlainText().strip(),
        }
