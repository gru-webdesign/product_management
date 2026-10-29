"""Svetla i tamna tema: boje (tokeni) za sve ekrane + Qt stylesheet.

Prikazi koji sami crtaju (Gant, Kanban, grafikon) uzimaju boje iz `tokens()` umesto da ih kucaju.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

FONTS_DIR = Path(__file__).resolve().parents[1] / "resources" / "fonts"
FONT_FAMILY = "Inter"


@dataclass(frozen=True)
class Tokens:
    name: str
    bg: str
    surface: str
    surface_alt: str
    sidebar: str
    border: str
    border_strong: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    danger: str
    danger_soft: str
    warning: str
    warning_soft: str
    success: str
    success_soft: str
    weekend: str
    today: str
    grid: str


LIGHT = Tokens(
    name="light",
    bg="#FCFCFD",
    surface="#FFFFFF",
    surface_alt="#F9F9FB",
    sidebar="#F5F5F7",
    border="#E4E4E9",
    border_strong="#CDCED6",
    text="#1C2024",
    muted="#60646C",
    faint="#8B8D98",
    accent="#5B5BD6",
    accent_hover="#5151CD",
    accent_soft="#EDEDFC",
    accent_text="#FFFFFF",
    danger="#DC3E42",
    danger_soft="#FEEBEC",
    warning="#E2730B",
    warning_soft="#FFEFD6",
    success="#2B9A66",
    success_soft="#E6F6EB",
    weekend="#F5F5F7",
    today="#E5484D",
    grid="#EEEEF1",
)

DARK = Tokens(
    name="dark",
    bg="#111113",
    surface="#18191B",
    surface_alt="#1D1E21",
    sidebar="#141416",
    border="#2B2D31",
    border_strong="#3C3F44",
    text="#EDEEF0",
    muted="#B0B4BA",
    faint="#777B84",
    accent="#6E6ADE",
    accent_hover="#7D79E8",
    accent_soft="#232350",
    accent_text="#FFFFFF",
    danger="#FF6369",
    danger_soft="#3B1219",
    warning="#FFA057",
    warning_soft="#331E0B",
    success="#3DD68C",
    success_soft="#132D21",
    weekend="#151618",
    today="#FF6369",
    grid="#222326",
)


class _ThemeManager(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.mode = "system"
        self.tokens = LIGHT

    def resolve(self, mode: str) -> Tokens:
        if mode == "dark":
            return DARK
        if mode == "light":
            return LIGHT
        scheme = QGuiApplication.styleHints().colorScheme()
        return DARK if scheme == Qt.ColorScheme.Dark else LIGHT


_manager: _ThemeManager | None = None


def manager() -> _ThemeManager:
    global _manager
    if _manager is None:
        _manager = _ThemeManager()
    return _manager


def tokens() -> Tokens:
    return manager().tokens


def load_fonts(app: QApplication) -> None:
    for file in sorted(FONTS_DIR.glob("*.otf")):
        QFontDatabase.addApplicationFont(str(file))
    font = QFont(FONT_FAMILY if FONT_FAMILY in QFontDatabase.families() else "Segoe UI")
    font.setPointSizeF(9.75)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)


def apply(app: QApplication, mode: str = "system") -> Tokens:
    m = manager()
    m.mode = mode
    t = m.resolve(mode)
    m.tokens = t
    app.setStyle("Fusion")
    app.setPalette(_palette(t))
    app.setStyleSheet(stylesheet(t))
    m.changed.emit()
    return t


def _palette(t: Tokens) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.surface,
        QPalette.ColorRole.AlternateBase: t.surface_alt,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.surface,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_text,
        QPalette.ColorRole.ToolTipBase: t.surface,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.PlaceholderText: t.faint,
        QPalette.ColorRole.Mid: t.border,
        QPalette.ColorRole.Midlight: t.border,
        QPalette.ColorRole.Dark: t.border_strong,
        QPalette.ColorRole.Link: t.accent,
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.faint))
    return p


def stylesheet(t: Tokens) -> str:
    return f"""
QWidget {{ color: {t.text}; }}
QMainWindow, QDialog {{ background: {t.bg}; }}
QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
    padding: 4px 6px; }}

#Sidebar {{ background: {t.sidebar}; border-right: 1px solid {t.border}; }}
#SidebarTitle {{ font-size: 11px; font-weight: 600; color: {t.faint};
    letter-spacing: 0.6px; }}
#AppName {{ font-size: 16px; font-weight: 600; }}
#ProjectList {{ background: transparent; border: none; outline: none; }}
#ProjectList::item {{ padding: 7px 8px; border-radius: 6px; margin: 1px 0; }}
#ProjectList::item:hover {{ background: {t.border}; }}
#ProjectList::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}

#Header {{ background: {t.bg}; border-bottom: 1px solid {t.border}; }}
#ProjectTitle {{ font-size: 18px; font-weight: 600; }}
#ProjectMeta, .muted, QLabel[muted="true"] {{ color: {t.muted}; }}
QLabel[faint="true"] {{ color: {t.faint}; }}
QLabel[heading="true"] {{ font-size: 13px; font-weight: 600; }}
#EmptyTitle {{ font-size: 17px; font-weight: 600; }}
#EmptyText {{ color: {t.muted}; }}

QPushButton {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 6px;
    padding: 5px 12px; min-height: 20px; }}
QPushButton:hover {{ background: {t.surface_alt}; border-color: {t.faint}; }}
QPushButton:pressed {{ background: {t.border}; }}
QPushButton:disabled {{ color: {t.faint}; border-color: {t.border}; }}
QPushButton[primary="true"] {{ background: {t.accent}; color: {t.accent_text};
    border: 1px solid {t.accent}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t.accent_hover}; }}
QPushButton[danger="true"] {{ color: {t.danger}; }}
QPushButton[flat="true"] {{ background: transparent; border: none; }}
QPushButton[flat="true"]:hover {{ background: {t.border}; }}
QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px 6px; }}
QToolButton:hover {{ background: {t.border}; }}
QToolButton:checked {{ background: {t.accent_soft}; color: {t.accent}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 6px;
    padding: 4px 8px; selection-background-color: {t.accent}; min-height: 20px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{ border: 1px solid {t.accent}; }}
QLineEdit:disabled, QDateEdit:disabled, QDoubleSpinBox:disabled {{ color: {t.faint};
    background: {t.surface_alt}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border};
    selection-background-color: {t.accent_soft}; selection-color: {t.text}; outline: none; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent; color: {t.muted}; }}
QTabBar::tab:hover {{ color: {t.text}; }}
QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; font-weight: 600; }}

QTreeView, QTableView, QListView {{ background: {t.surface}; border: 1px solid {t.border};
    border-radius: 8px; alternate-background-color: {t.surface_alt}; outline: none;
    selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}
QTreeView::item, QTableView::item {{ padding: 4px 4px; border: none; }}
QTreeView::item:selected, QTableView::item:selected {{ background: {t.accent_soft};
    color: {t.text}; }}
QHeaderView {{ background: {t.surface}; }}
QHeaderView::section {{ background: {t.surface}; color: {t.muted}; border: none;
    border-bottom: 1px solid {t.border}; padding: 6px 8px; font-weight: 600; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t.border_strong}; border-radius: 3px; min-height: 24px;
    min-width: 24px; }}
QScrollBar::handle:hover {{ background: {t.faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {t.border}; border: none; border-radius: 3px; height: 6px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
QProgressBar[state="warn"]::chunk {{ background: {t.warning}; }}
QProgressBar[state="over"]::chunk {{ background: {t.danger}; }}

QMenu {{ background: {t.surface}; border: 1px solid {t.border}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QMenuBar {{ background: {t.bg}; }}
QMenuBar::item:selected {{ background: {t.border}; }}
QStatusBar {{ background: {t.sidebar}; color: {t.muted}; border-top: 1px solid {t.border}; }}
QSplitter::handle {{ background: {t.border}; }}
QCheckBox {{ spacing: 6px; }}
QGroupBox {{ border: 1px solid {t.border}; border-radius: 8px; margin-top: 14px;
    padding: 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}

#Card {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; }}
#Banner[level="warn"] {{ background: {t.warning_soft}; border: 1px solid {t.warning};
    border-radius: 8px; }}
#Banner[level="over"] {{ background: {t.danger_soft}; border: 1px solid {t.danger};
    border-radius: 8px; }}
#KpiValue {{ font-size: 18px; font-weight: 600; }}
#KpiLabel {{ color: {t.muted}; font-size: 11px; }}
"""


def repolish(widget) -> None:
    """Primeni stil ponovo posle promene dinamičkog svojstva (npr. setProperty('state', ...))."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
