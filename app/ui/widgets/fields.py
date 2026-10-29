"""Polja za forme: opcioni datum, iznos novca, izbor boje."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QCheckBox,
    QDateEdit,
    QHBoxLayout,
    QLineEdit,
    QWidget,
)

from app.services.money import format_money, to_minor
from app.ui import theme

DATE_FORMAT = "dd.MM.yyyy."


def to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def from_qdate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def date_edit(value: date | None = None) -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat(DATE_FORMAT)
    edit.setDate(to_qdate(value or date.today()))
    return edit


class OptionalDateField(QWidget):
    """Datum koji može i da ne postoji (kvačica isključuje polje)."""

    changed = Signal()

    def __init__(self, value: date | None = None, label: str = "", parent=None) -> None:
        super().__init__(parent)
        self.check = QCheckBox(label)
        self.edit = date_edit(value)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self.check)
        lay.addWidget(self.edit, 1)
        self.check.toggled.connect(self._sync)
        self.edit.dateChanged.connect(lambda _q: self.changed.emit())
        self.set_value(value)

    def _sync(self) -> None:
        self.edit.setEnabled(self.check.isChecked())
        self.changed.emit()

    def set_value(self, value: date | None) -> None:
        self.check.setChecked(value is not None)
        if value is not None:
            self.edit.setDate(to_qdate(value))
        self._sync()

    def value(self) -> date | None:
        return from_qdate(self.edit.date()) if self.check.isChecked() else None


def parse_amount(text: str) -> Decimal:
    """Prihvata '1.234,56', '1234,56', '1234.56', '1 234' → Decimal."""
    t = text.strip().replace(" ", "").replace(" ", "")
    for cur in ("RSD", "EUR", "USD", "din", "€"):
        t = t.replace(cur, "")
    if not t:
        return Decimal("0")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    elif "." in t and len(t.split(".")[1]) == 3:
        t = t.replace(".", "")  # "1.500" = hiljadu petsto
    try:
        value = Decimal(t)
    except InvalidOperation as exc:
        raise ValueError(f"'{text}' nije ispravan iznos") from exc
    if value < 0:
        raise ValueError("Iznos ne može biti negativan")
    return value


class MoneyEdit(QLineEdit):
    """Unos iznosa u srpskom formatu; value_minor() vraća iznos u parama/centima."""

    def __init__(self, minor: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setPlaceholderText("0,00")
        self.set_minor(minor)
        self.editingFinished.connect(self._reformat)

    def set_minor(self, minor: int) -> None:
        self.setText(format_money(minor, "").strip() if minor else "")

    def value_minor(self) -> int:
        return to_minor(parse_amount(self.text()))

    def is_valid(self) -> bool:
        try:
            self.value_minor()
            return True
        except ValueError:
            return False

    def _reformat(self) -> None:
        if self.is_valid():
            self.set_minor(self.value_minor())


class _Swatch(QAbstractButton):
    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self.color = color
        self.setCheckable(True)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isChecked():
            p.setPen(QColor(theme.tokens().text))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(1, 1, 22, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(4, 4, 16, 16)


class ColorPicker(QWidget):
    def __init__(self, colors: list[str], value: str | None = None, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.swatches: list[_Swatch] = []
        for c in colors:
            sw = _Swatch(c)
            self.group.addButton(sw)
            lay.addWidget(sw)
            self.swatches.append(sw)
        lay.addStretch(1)
        self.set_value(value or colors[0])

    def set_value(self, color: str) -> None:
        for sw in self.swatches:
            if sw.color.lower() == color.lower():
                sw.setChecked(True)
                return
        self.swatches[0].setChecked(True)

    def value(self) -> str:
        checked = self.group.checkedButton()
        return checked.color if checked else self.swatches[0].color
