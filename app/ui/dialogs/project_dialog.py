"""Dijalog za novi projekat ili izmenu postojećeg."""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit

from app.db.models import Project, ProjectStatus
from app.labels import PROJECT_COLORS, PROJECT_STATUS
from app.services.templates import TemplateInfo
from app.ui.dialogs.base import FormDialog
from app.ui.widgets.fields import ColorPicker, OptionalDateField


class ProjectDialog(FormDialog):
    def __init__(
        self,
        project: Project | None = None,
        parent=None,
        templates: list[TemplateInfo] | None = None,
    ) -> None:
        super().__init__("Izmena projekta" if project else "Novi projekat", parent)
        self.template = None
        if project is None and templates:
            self.template = QComboBox()
            self.template.addItem("Prazan projekat", None)
            for info in templates:
                kind = "" if info.builtin else "  (moj)"
                self.template.addItem(f"{info.name}{kind}, {info.task_count} zadataka", info.id)
                self.template.setItemData(
                    self.template.count() - 1, info.description, Qt.ItemDataRole.ToolTipRole
                )

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

        if self.template is not None:
            self.form.addRow("Šablon", self.template)
            self.template.currentIndexChanged.connect(self._template_changed)
        self.form.addRow("Naziv", self.name)
        self.form.addRow("Klijent", self.client)
        self.form.addRow("Boja", self.color)
        self.form.addRow("Status", self.status)
        self.form.addRow("Početak", self.start)
        self.form.addRow("Kraj", self.end)
        self.form.addRow("Opis", self.description)
        self.name.setFocus()

    def _template_changed(self) -> None:
        # Šablon raspoređuje zadatke od početka projekta, pa početak mora da postoji.
        if self.template.currentData() and self.start.value() is None:
            self.start.set_value(date.today())

    def template_id(self) -> str | None:
        return self.template.currentData() if self.template is not None else None

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
