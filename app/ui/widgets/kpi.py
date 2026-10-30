"""Ikonica u obojenom kvadratu i kartica sa jednom brojkom (Pregled, Budžet)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from app.ui import icons, theme
from app.ui.widgets.card import Card


class IconChip(QLabel):
    """Ikonica u obojenom kvadratu (ton: accent / success / warning / danger)."""

    def __init__(self, name: str, tone: str = "accent", size: int = 38, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("IconChip")
        self.name = name
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_tone(tone)
        theme.manager().changed.connect(self._refresh)

    def set_tone(self, tone: str) -> None:
        self.tone = tone
        self.setProperty("tone", tone)
        theme.repolish(self)
        self._refresh()

    def _refresh(self) -> None:
        t = theme.tokens()
        color = {"success": t.success, "warning": t.warning, "danger": t.danger}.get(
            self.tone, t.accent
        )
        self.setPixmap(icons.icon(self.name, color).pixmap(18, 18))


class KpiCard(Card):
    """Ikonica i naziv gore, brojka ispod preko cele širine, napomena na dnu."""

    def __init__(
        self, label: str, icon_name: str, tone: str = "accent", parent=None, small: bool = False
    ) -> None:
        super().__init__(parent=parent, padding=(18, 16, 18, 16))
        top = QHBoxLayout()
        top.setSpacing(10)
        self.chip = IconChip(icon_name, tone, 34)
        self.label = QLabel(label)
        self.label.setObjectName("KpiLabel")
        top.addWidget(self.chip)
        top.addWidget(self.label, 1)
        self.body.addLayout(top)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.value = QLabel("0")
        self.value.setObjectName("KpiValueSmall" if small else "KpiValue")
        self.note = QLabel()
        self.note.setObjectName("KpiNote")
        self.sub = self.note
        text.addWidget(self.value)
        text.addWidget(self.note)
        self.body.addLayout(text)

    def set(self, value: str, note: str = "", color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.note.setText(note)
