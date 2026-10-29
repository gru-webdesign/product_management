"""Ikonice: Phosphor Icons (regular, MIT licenca, app/resources/icons/phosphor), obojene po temi.

Ime u aplikaciji (npr. "gantt") = ime fajla u folderu phosphor/. Nova ikonica: kopiraj SVG iz
paketa @phosphor-icons/core (assets/regular) pod imenom koje koristiš ovde.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui import theme

ICONS_DIR = Path(__file__).resolve().parents[1] / "resources" / "icons" / "phosphor"


@lru_cache(maxsize=128)
def _source(name: str) -> str:
    return (ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")


def svg(name: str, color: str) -> str:
    return _source(name).replace('fill="currentColor"', f'fill="{color}"', 1)


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
    return sorted(p.stem for p in ICONS_DIR.glob("*.svg"))
