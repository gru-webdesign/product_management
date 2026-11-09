"""Ikonica u obojenom kvadratu i kartica sa jednom brojkom (Pregled, Budžet)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

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
        pad = (14, 14, 14, 14) if small else (18, 16, 18, 16)
        super().__init__(parent=parent, padding=pad)
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
        self.note.setWordWrap(True)  # duga napomena ide u novi red, ne širi karticu
        self.sub = self.note
        text.addWidget(self.value)
        text.addWidget(self.note)
        self.body.addLayout(text)

    def set(self, value: str, note: str = "", color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.note.setText(note)


class KpiRow(QWidget):
    """Red KPI kartica koji se prelomi u više redova kad nema mesta (uzak prozor, veći font).

    Kartica se nikad ne sužava ispod širine koju traži njena brojka, pa se iznos ne seče.
    """

    def __init__(self, cards: list[QWidget], spacing: int = 2, parent=None) -> None:
        super().__init__(parent)
        self.cards = cards
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(spacing)
        self._columns = 0
        self._place(len(cards))

    def _needed(self) -> int:
        return max(c.minimumSizeHint().width() for c in self.cards) + self.grid.spacing()

    def _place(self, columns: int) -> None:
        columns = max(1, min(columns, len(self.cards)))
        if columns == self._columns:
            return
        self._columns = columns
        for c in self.cards:
            self.grid.removeWidget(c)
        for i in range(self.grid.columnCount()):
            self.grid.setColumnStretch(i, 0)
        for i, c in enumerate(self.cards):
            self.grid.addWidget(c, i // columns, i % columns)
        for i in range(columns):
            self.grid.setColumnStretch(i, 1)

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        hint.setWidth(self._needed())
        return hint

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place(self.width() // max(1, self._needed()))

    def refit(self) -> None:
        """Posle promene teksta (npr. veći iznos) proveri da li i dalje staje.

        Odlaže se dok Qt ne preračuna veličine kartica sa novim tekstom.
        """
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._refit_now)

    def _refit_now(self) -> None:
        for c in self.cards:
            c.layout().activate()
        self._columns = 0
        self._place(self.width() // max(1, self._needed()) if self.width() else len(self.cards))
        self.updateGeometry()
