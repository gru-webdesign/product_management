"""Kartica sa mekom senkom, bez QGraphicsEffect-a (brže, ne smeta tabelama i Gantu).

Senka se crta u marginama same kartice: oko površine ostaje nekoliko piksela praznog prostora
u kojem se slojevito iscrta senka. Sadržaj ide u `body` (QVBoxLayout).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.ui import icons, theme

# prostor za senku oko površine (levo, gore, desno, dole)
SHADOW = (8, 6, 8, 12)
RADIUS = 12


def paint_card(
    p: QPainter,
    rect: QRectF,
    radius: float = RADIUS,
    fill: str | None = None,
    border: str | None = None,
    lift: float = 1.0,
) -> None:
    """Površina kartice sa senkom; koriste je i prikazi koji sami crtaju (Kanban)."""
    t = theme.tokens()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    steps = 7
    base = QColor(t.shadow)
    for i in range(steps, 0, -1):
        c = QColor(base)
        c.setAlpha(int(t.shadow_alpha * lift * ((steps - i + 1) / steps) ** 2 / steps * 1.6))
        p.setBrush(c)
        grow = i * 1.1
        p.drawRoundedRect(
            rect.adjusted(-grow, -grow + 2 * lift, grow, grow + 3 * lift),
            radius + grow,
            radius + grow,
        )
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.fillPath(path, QColor(fill or t.surface))
    p.setPen(QPen(QColor(border or t.border), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.restore()


class Card(QFrame):
    """Kartica: opcioni naslov (sa ikonicom i desnim dodatkom) i telo."""

    def __init__(
        self,
        title: str = "",
        parent: QWidget | None = None,
        padding: tuple[int, int, int, int] = (18, 16, 18, 16),
        icon: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        pl, pt, pr, pb = padding
        sl, st, sr, sb = SHADOW
        outer = QVBoxLayout(self)
        outer.setContentsMargins(sl + pl, st + pt, sr + pr, sb + pb)
        outer.setSpacing(12)
        self.head = QHBoxLayout()
        self.head.setSpacing(8)
        self.icon_label: QLabel | None = None
        self._icon_name = icon
        self.title_label: QLabel | None = None
        if title:
            if icon:
                self.icon_label = QLabel()
                self.head.addWidget(self.icon_label)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("CardTitle")
            self.head.addWidget(self.title_label)
            self.head.addStretch(1)
            outer.addLayout(self.head)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self.body.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body, 1)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        theme.manager().changed.connect(self._theme_changed)
        self._theme_changed()

    def _theme_changed(self) -> None:
        if self.icon_label is not None and self._icon_name:
            self.icon_label.setPixmap(
                icons.icon(self._icon_name, theme.tokens().accent).pixmap(16, 16)
            )
        self.update()

    def add_head_widget(self, widget: QWidget) -> None:
        self.head.addWidget(widget)

    def surface_rect(self) -> QRectF:
        sl, st, sr, sb = SHADOW
        return QRectF(self.rect()).adjusted(sl, st, -sr, -sb)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_card(p, self.surface_rect())
        p.end()
