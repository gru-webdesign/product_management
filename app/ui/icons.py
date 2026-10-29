"""Mali skup linijskih ikonica (sopstvene SVG putanje, 24×24), obojenih po temi."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui import theme

_PATHS = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/>',
    "share": '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/>'
    '<circle cx="18" cy="18" r="2.5"/><path d="M8.2 10.8l7.6-3.6M8.2 13.2l7.6 3.6"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21'
    'M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/>'
    '<circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
    "kanban": '<rect x="3.5" y="4" width="5" height="16" rx="1.5"/>'
    '<rect x="10" y="4" width="5" height="11" rx="1.5"/>'
    '<rect x="16.5" y="4" width="4" height="7" rx="1.5"/>',
    "gantt": '<path d="M4 4v16h16"/><rect x="7" y="6.5" width="8" height="3" rx="1"/>'
    '<rect x="10" y="11" width="9" height="3" rx="1"/><rect x="7" y="15.5" width="5" height="2.5" rx="1"/>',
    "wallet": '<rect x="3.5" y="6" width="17" height="13" rx="2"/>'
    '<path d="M3.5 9.5h17M15.5 14h2"/>',
    "archive": '<rect x="3.5" y="4.5" width="17" height="4" rx="1"/>'
    '<path d="M5 8.5V19a1 1 0 001 1h12a1 1 0 001-1V8.5M10 12.5h4"/>',
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/>',
    "edit": '<path d="M4.5 19.5l1-4L15.5 5.5l3 3-10 10z"/><path d="M13.5 7.5l3 3"/>',
    "comment": '<path d="M4.5 5.5h15v10h-9l-4 3.5v-3.5h-2z"/>',
    "link": '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/>'
    '<path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',
    "refresh": '<path d="M19.5 12a7.5 7.5 0 11-2.2-5.3M19.5 4.5v4h-4"/>',
    "download": '<path d="M12 4v11M7 10.5l5 5 5-5M5 19.5h14"/>',
    "chevron-down": '<path d="M6.5 9.5l5.5 5.5 5.5-5.5"/>',
    "calendar": '<rect x="4" y="5.5" width="16" height="14" rx="2"/>'
    '<path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    "folder": '<path d="M3.5 7a1.5 1.5 0 011.5-1.5h4.5l2 2.5H19a1.5 1.5 0 011.5 1.5v8A1.5 1.5 0 0119 19'
    'H5a1.5 1.5 0 01-1.5-1.5z"/>',
    "today": '<path d="M12 3.5v17"/><circle cx="12" cy="12" r="2.5"/>',
    "zoom-in": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4M8.5 11h5M11 8.5v5"/>',
    "zoom-out": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4M8.5 11h5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "x": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "more": '<circle cx="6" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/>'
    '<circle cx="18" cy="12" r="1.2"/>',
    "milestone": '<path d="M12 4l8 8-8 8-8-8z"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8.5 10.5V8a3.5 3.5 0 017 0v2.5"/>',
}


def svg(name: str, color: str, stroke: float = 1.75) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{_PATHS[name]}</svg>'
    )


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, ratio: float) -> QPixmap:
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode()))
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px.width(), px.height()))
    painter.end()
    px.setDevicePixelRatio(ratio)
    return px


def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    t = theme.tokens()
    ic = QIcon()
    for ratio in (1.0, 2.0):
        ic.addPixmap(_pixmap(name, color or t.muted, size, ratio), QIcon.Mode.Normal)
        ic.addPixmap(_pixmap(name, t.faint, size, ratio), QIcon.Mode.Disabled)
    return ic


def names() -> list[str]:
    return sorted(_PATHS)
