"""Kartica sa mekom senkom, bez QGraphicsEffect-a (brže, ne smeta tabelama i Gantu).

Senka se crta u marginama same kartice: oko površine ostaje nekoliko piksela praznog prostora
u kojem se slojevito iscrta senka. Sadržaj ide u `body` (QVBoxLayout).
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.ui import icons, theme

# prostor za senku oko površine (levo, gore, desno, dole)
SHADOW = (8, 6, 8, 12)
RADIUS = 12


_CACHE: OrderedDict[tuple, QPixmap] = OrderedDict()
_CACHE_MAX = 96


def paint_card(
    p: QPainter,
    rect: QRectF,
    radius: float = RADIUS,
    fill: str | None = None,
    border: str | None = None,
    lift: float = 1.0,
) -> None:
    """Površina kartice sa senkom; koriste je i prikazi koji sami crtaju (Kanban).

    Senka je skupa za crtanje (više slojeva sa zaobljenim ivicama), pa se iscrta jednom u
    sliku po veličini i boji i posle se samo kopira. Tako pomeranje miša i skrol ne troše CPU.
    """
    t = theme.tokens()
    fill = fill or t.surface
    border = border or t.border
    pad_l, pad_t, pad_r, pad_b = 12, 10, 12, 16
    w, h = int(round(rect.width())), int(round(rect.height()))
    if w <= 0 or h <= 0:
        return
    dpr = p.device().devicePixelRatioF() if p.device() is not None else 1.0
    key = (w, h, radius, fill, border, round(lift, 2), t.shadow, t.shadow_alpha, dpr)
    pix = _CACHE.get(key)
    if pix is None:
        pix = QPixmap(int((w + pad_l + pad_r) * dpr), int((h + pad_t + pad_b) * dpr))
        pix.setDevicePixelRatio(dpr)
        pix.fill(Qt.GlobalColor.transparent)
        q = QPainter(pix)
        _paint_card_direct(q, QRectF(pad_l, pad_t, w, h), radius, fill, border, lift)
        q.end()
        _CACHE[key] = pix
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    else:
        _CACHE.move_to_end(key)
    p.drawPixmap(QPointF(rect.left() - pad_l, rect.top() - pad_t), pix)


def _paint_card_direct(
    p: QPainter, rect: QRectF, radius: float, fill: str, border: str, lift: float
) -> None:
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
    p.fillPath(path, QColor(fill))
    p.setPen(QPen(QColor(border), 1))
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
