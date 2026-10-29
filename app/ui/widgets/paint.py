"""Pomoćne funkcije za crtanje (bedž statusa, traka progresa) u tabelama, Kanbanu i Gantu."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from app.ui import theme


def soft(color: str, alpha: int = 38) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def draw_pill(p: QPainter, rect: QRect, text: str, color: str, font: QFont | None = None) -> int:
    """Nacrta zaobljeni bedž sa tačkom u boji; vraća širinu."""
    f = QFont(font or p.font())
    f.setPointSizeF(max(7.5, f.pointSizeF() - 0.75))
    f.setWeight(QFont.Weight.Medium)
    fm = QFontMetrics(f)
    w = fm.horizontalAdvance(text) + 24
    h = min(rect.height() - 4, fm.height() + 6)
    r = QRectF(rect.left(), rect.center().y() - h / 2 + 0.5, w, h)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(soft(color, 34 if theme.tokens().name == "light" else 60))
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(r.left() + 8, r.center().y() - 3, 6, 6))
    p.setFont(f)
    p.setPen(QColor(theme.tokens().text))
    p.drawText(r.adjusted(18, 0, -4, 0), Qt.AlignmentFlag.AlignVCenter, text)
    p.restore()
    return w


def draw_progress(
    p: QPainter, rect: QRect, pct: int, color: str | None = None, label: bool = True
) -> None:
    t = theme.tokens()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bar_w = rect.width() - (40 if label else 0)
    bar = QRectF(rect.left(), rect.center().y() - 3, max(10, bar_w), 6)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t.border))
    p.drawRoundedRect(bar, 3, 3)
    if pct > 0:
        fill = QRectF(bar.left(), bar.top(), bar.width() * min(pct, 100) / 100, bar.height())
        p.setBrush(QColor(color or (t.success if pct >= 100 else t.accent)))
        p.drawRoundedRect(fill, 3, 3)
    if label:
        p.setPen(QColor(t.muted))
        p.drawText(
            QRect(int(bar.right()) + 6, rect.top(), 36, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"{pct}%",
        )
    p.restore()


class _Base(QStyledItemDelegate):
    def paint_background(self, p: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        opt.icon = opt.icon.__class__()
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, p, opt.widget)


class PillDelegate(_Base):
    """Kolona sa bedžom; tekst iz DisplayRole, boja iz UserRole+1."""

    COLOR_ROLE = Qt.ItemDataRole.UserRole + 1

    def paint(self, p, option, index) -> None:
        self.paint_background(p, option, index)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        color = index.data(self.COLOR_ROLE)
        if text and color:
            draw_pill(p, option.rect.adjusted(6, 0, -4, 0), text, color, option.font)


class ProgressDelegate(_Base):
    """Kolona sa trakom progresa; vrednost (0–100) iz UserRole+1."""

    VALUE_ROLE = Qt.ItemDataRole.UserRole + 1
    COLOR_ROLE = Qt.ItemDataRole.UserRole + 3

    def paint(self, p, option, index) -> None:
        self.paint_background(p, option, index)
        value = index.data(self.VALUE_ROLE)
        if value is not None:
            draw_progress(
                p, option.rect.adjusted(8, 0, -6, 0), int(value), index.data(self.COLOR_ROLE)
            )
