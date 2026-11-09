"""Labela u jednom redu koja se, kad nema mesta, skrati sa „…“ (pun tekst je u opisu)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None, min_chars: int = 8) -> None:
        super().__init__(parent)
        self._full = ""
        self._min_chars = min_chars
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text or ""
        self.setToolTip(self._full)
        self._elide()
        self.updateGeometry()

    def text(self) -> str:
        return self._full

    def fullText(self) -> str:  # noqa: N802
        return self._full

    def _elide(self) -> None:
        width = max(0, self.contentsRect().width())
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, width)
        super().setText(shown if width else self._full)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._full) + 2, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(fm.averageCharWidth() * self._min_chars, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        self._elide()
