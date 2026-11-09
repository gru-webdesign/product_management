"""Raspored koji ređa elemente u red i prelama ih u novi red kad nema mesta.

Koristi se za trake sa filterima i dugmićima: na uskom prozoru ili sa uvećanim fontom (125%,
150% na Windows-u) ništa se ne seče i prozor ne mora da bude širok.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h = spacing
        self._v = v_spacing
        self._right_from: int | None = None  # elementi od ovog indeksa idu desno
        self.setContentsMargins(0, 0, 0, 0)

    # --- API kao QHBoxLayout ---
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def addStretch(self, _stretch: int = 1) -> None:  # noqa: N802
        """Sve dodato posle ovoga se poravnava desno (kao stretch u QHBoxLayout-u)."""
        self._right_from = len(self._items)

    def addSpacing(self, _size: int) -> None:  # noqa: N802
        pass

    def setSpacing(self, spacing: int) -> None:  # noqa: N802
        self._h = spacing

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            if self._right_from is not None and index < self._right_from:
                self._right_from -= 1
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        w = h = 0
        for item in self._visible():
            hint = _hint(item)
            w += hint.width() + self._h
            h = max(h, hint.height())
        m = self.contentsMargins()
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._visible():
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    # --- raspoređivanje ---
    def _visible(self) -> list[QLayoutItem]:
        out = []
        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            out.append(item)
        return out

    def _do_layout(self, rect: QRect, apply: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        rows: list[list[tuple[QLayoutItem, QSize]]] = [[]]
        x = 0
        visible = self._visible()
        right_items = set()
        if self._right_from is not None:
            right_items = {id(i) for i in self._items[self._right_from :]}
        for item in visible:
            hint = _hint(item)
            hint.setWidth(min(hint.width(), max(1, area.width())))
            if rows[-1] and x + hint.width() > area.width():
                rows.append([])
                x = 0
            rows[-1].append((item, hint))
            x += hint.width() + self._h
        y = area.y()
        for row in rows:
            if not row:
                continue
            height = max(h.height() for _, h in row)
            if apply:
                left = [(i, h) for i, h in row if id(i) not in right_items]
                right = [(i, h) for i, h in row if id(i) in right_items]
                x = area.x()
                for item, hint in left:
                    item.setGeometry(QRect(QPoint(x, y + (height - hint.height()) // 2), hint))
                    x += hint.width() + self._h
                x = area.right() + 1
                for item, hint in reversed(right):
                    x -= hint.width()
                    item.setGeometry(QRect(QPoint(x, y + (height - hint.height()) // 2), hint))
                    x -= self._h
            y += height + self._v
        return y - self._v - rect.y() + m.bottom()


def _hint(item: QLayoutItem) -> QSize:
    """Veličina pitana direktno od widget-a (keš stavke kasni posle setText)."""
    w = item.widget()
    if w is not None:
        hint = w.sizeHint().expandedTo(w.minimumSizeHint())
        return hint.expandedTo(w.minimumSize()).boundedTo(w.maximumSize())
    return item.sizeHint().expandedTo(item.minimumSize())


def flow_widget(spacing: int = 8) -> tuple[QWidget, FlowLayout]:
    """Prazan widget sa FlowLayout-om (za ubacivanje u postojeći vertikalni raspored)."""
    w = QWidget()
    w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    lay = FlowLayout(w, spacing)
    return w, lay
