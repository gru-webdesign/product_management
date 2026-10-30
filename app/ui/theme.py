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
FONT_FAMILY = "Geist"
MONO_FAMILY = "Geist Mono"


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
    # glavno dugme (svetla: teget sa belim tekstom, tamna: belo sa teget tekstom)
    primary: str
    primary_hover: str
    primary_text: str
    # sidebar je teget u obe teme
    sidebar_text: str
    sidebar_muted: str
    sidebar_hover: str
    sidebar_active: str
    sidebar_border: str
    # senka kartica: boja i jačina (0-255)
    shadow: str
    shadow_alpha: int
    # podloga Kanban kolona (između pozadine i kartice)
    lane: str


# Teget i belo: svetla tema ima belu radnu površinu i teget sidebar, tamna je cela u tegetu.
# Plava (accent) je za podatke i izbor (napredak, trake, aktivna stavka), dugmad su teget/bela.
LIGHT = Tokens(
    name="light",
    bg="#F2F4F9",
    surface="#FFFFFF",
    surface_alt="#F6F8FC",
    sidebar="#0B1638",
    border="#E3E7F0",
    border_strong="#CCD3E2",
    text="#0E1730",
    muted="#5A6480",
    faint="#8B93AB",
    accent="#2F55D4",
    accent_hover="#2648C0",
    accent_soft="#E8EEFD",
    accent_text="#FFFFFF",
    danger="#D23434",
    danger_soft="#FCECEC",
    warning="#B8620A",
    warning_soft="#FCF0E1",
    success="#1F8A55",
    success_soft="#E4F4EB",
    weekend="#F5F7FB",
    today="#D23434",
    grid="#EDF0F6",
    primary="#13224F",
    primary_hover="#1D3170",
    primary_text="#FFFFFF",
    sidebar_text="#E9EDF8",
    sidebar_muted="#8E9BBF",
    sidebar_hover="#14224A",
    sidebar_active="#1E3061",
    sidebar_border="#0B1638",
    shadow="#13224F",
    shadow_alpha=26,
    lane="#E8ECF4",
)

DARK = Tokens(
    name="dark",
    bg="#0A1128",
    surface="#111B38",
    surface_alt="#16224A",
    sidebar="#070D20",
    border="#1E2B52",
    border_strong="#2B3B68",
    text="#F3F5FB",
    muted="#9CA7C6",
    faint="#67739A",
    accent="#6F95FF",
    accent_hover="#88A8FF",
    accent_soft="#1B2B5A",
    accent_text="#081024",
    danger="#FF6B6B",
    danger_soft="#3A1A2C",
    warning="#F5A524",
    warning_soft="#33290F",
    success="#3DD68C",
    success_soft="#0F3030",
    weekend="#0D1633",
    today="#FF6B6B",
    grid="#18244A",
    primary="#FFFFFF",
    primary_hover="#E2E8F6",
    primary_text="#0A1128",
    sidebar_text="#E9EDF8",
    sidebar_muted="#7D89AD",
    sidebar_hover="#0F1934",
    sidebar_active="#17244B",
    sidebar_border="#141E3D",
    shadow="#000000",
    shadow_alpha=90,
    lane="#0D1633",
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
    for file in sorted(FONTS_DIR.glob("*.ttf")):
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


# Uglovi: kontrole (dugmad, polja, tabovi) 8px, kartice 12px, ugnježdeno 10px, bedževi puni.
# Kartice (widgets/card.py) same crtaju površinu i senku, pa ovde nemaju pozadinu.
def stylesheet(t: Tokens) -> str:
    return f"""
QWidget {{ color: {t.text}; }}
QMainWindow, QDialog {{ background: {t.bg}; }}
QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
    padding: 5px 8px; border-radius: 6px; }}

#Sidebar {{ background: {t.sidebar}; border-right: 1px solid {t.sidebar_border}; }}
#Sidebar QLabel, #Sidebar QCheckBox {{ color: {t.sidebar_text}; }}
#SidebarTitle {{ font-size: 12px; font-weight: 500; color: {t.sidebar_muted}; }}
#Sidebar QLabel#SidebarTitle {{ color: {t.sidebar_muted}; }}
#AppName {{ font-size: 17px; font-weight: 600; letter-spacing: -0.2px; }}
#AppTagline {{ font-size: 11px; }}
#Sidebar QLabel#AppTagline {{ color: {t.sidebar_muted}; }}
#Sidebar QToolButton {{ color: {t.sidebar_text}; border-radius: 8px; padding: 6px 8px; }}
#Sidebar QToolButton:hover {{ background: {t.sidebar_hover}; }}
#NavButton {{ text-align: left; padding: 9px 10px; border-radius: 8px; font-weight: 500; }}
#Sidebar QToolButton#NavButton:checked {{ background: {t.sidebar_active}; color: #FFFFFF; }}
#ProjectList {{ background: transparent; border: none; outline: none; color: {t.sidebar_text}; }}
#Sidebar QCheckBox::indicator {{ background: transparent; border-color: {t.sidebar_muted}; }}
#Sidebar QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
#SidebarFooter {{ border-top: 1px solid {t.sidebar_border}; }}

#Header {{ background: transparent; }}
#ProjectTitle {{ font-size: 24px; font-weight: 600; letter-spacing: -0.4px; }}
#PageSubtitle {{ color: {t.muted}; }}
#ProjectMeta, .muted, QLabel[muted="true"] {{ color: {t.muted}; }}
#StatusChip {{ background: {t.accent_soft}; color: {t.accent}; border-radius: 10px;
    padding: 2px 10px; font-weight: 600; font-size: 12px; }}
QLabel[faint="true"] {{ color: {t.faint}; }}
QLabel[heading="true"], #CardTitle {{ font-size: 14px; font-weight: 600; }}
#EmptyTitle {{ font-size: 20px; font-weight: 600; }}
#EmptyText {{ color: {t.muted}; }}

QPushButton {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px;
    padding: 6px 14px; min-height: 20px; font-weight: 500; }}
QPushButton:hover {{ background: {t.surface_alt}; border-color: {t.faint}; }}
QPushButton:pressed {{ background: {t.border}; }}
QPushButton:disabled {{ color: {t.faint}; border-color: {t.border}; }}
QPushButton[primary="true"] {{ background: {t.primary}; color: {t.primary_text};
    border: 1px solid {t.primary}; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: {t.primary_hover};
    border-color: {t.primary_hover}; }}
QPushButton[danger="true"] {{ color: {t.danger}; }}
QPushButton[primary="true"]:disabled {{ background: {t.border}; color: {t.faint};
    border-color: {t.border}; }}
QPushButton[danger="true"]:disabled {{ color: {t.faint}; }}
QPushButton[link="true"] {{ background: transparent; border: none; color: {t.accent};
    padding: 0; text-align: left; font-weight: 500; }}
QPushButton[link="true"]:hover {{ text-decoration: underline; background: transparent; }}
QPushButton[flat="true"] {{ background: transparent; border: none; }}
QPushButton[flat="true"]:hover {{ background: {t.surface_alt}; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 5px 7px; }}
QToolButton:hover {{ background: {t.surface_alt}; }}
QToolButton:checked {{ background: {t.accent_soft}; color: {t.accent}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px;
    padding: 5px 9px; selection-background-color: {t.accent}; min-height: 20px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{ border: 1px solid {t.accent}; }}
QLineEdit:disabled, QDateEdit:disabled, QDoubleSpinBox:disabled {{ color: {t.faint};
    background: {t.surface_alt}; }}
QLineEdit#SearchField {{ border-radius: 18px; padding: 7px 12px; background: {t.surface};
    border-color: {t.border}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 22px;
    subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({_chevron(t)}); width: 12px;
    height: 12px; }}
QComboBox {{ padding-right: 24px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; border: none; }}
QDateEdit::up-button, QDateEdit::down-button {{ width: 0; }}
QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border};
    selection-background-color: {t.accent_soft}; selection-color: {t.text}; outline: none;
    padding: 4px; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 7px 14px; margin-right: 4px; border: 1px solid
    transparent; border-radius: 8px; color: {t.muted}; font-weight: 500; }}
QTabBar::tab:hover {{ color: {t.text}; background: {t.surface_alt}; }}
QTabBar::tab:selected {{ color: {t.text}; background: {t.surface}; border: 1px solid {t.border};
    font-weight: 600; }}
QTabWidget#ViewTabs > QTabBar::tab {{ padding: 8px 16px; }}

QTreeView, QTableView, QListView {{ background: {t.surface}; border: 1px solid {t.border};
    border-radius: 12px; alternate-background-color: {t.surface_alt}; outline: none;
    selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}
QTreeView::item, QTableView::item {{ padding: 6px 4px; border: none; }}
QTreeView::item:hover {{ background: {t.surface_alt}; }}
QTreeView::item:selected, QTableView::item:selected {{ background: {t.accent_soft};
    color: {t.text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {t.muted}; border: none;
    border-bottom: 1px solid {t.border}; padding: 8px 8px; font-weight: 500; font-size: 12px; }}
#Card QTreeView, #Card QTableView, #Card QListView, #Card QListWidget {{ border: none;
    background: transparent; border-radius: 0; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t.border_strong}; border-radius: 3px; min-height: 24px;
    min-width: 24px; }}
QScrollBar::handle:hover {{ background: {t.faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget#ScrollBody {{ background: transparent; }}

QProgressBar {{ background: {t.surface_alt}; border: none; border-radius: 3px; height: 6px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
QProgressBar[state="warn"]::chunk {{ background: {t.warning}; }}
QProgressBar[state="over"]::chunk {{ background: {t.danger}; }}
QProgressBar[state="done"]::chunk {{ background: {t.success}; }}

QMenu {{ background: {t.surface}; border: 1px solid {t.border}; padding: 5px;
    border-radius: 10px; }}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QMenuBar {{ background: {t.bg}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 4px 8px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {t.surface_alt}; }}
QStatusBar {{ background: {t.bg}; color: {t.faint}; border-top: 1px solid {t.border}; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: transparent; }}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {t.border_strong};
    border-radius: 4px; background: {t.surface}; }}
QCheckBox::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent};
    image: url({_icon("check-white")}); }}
QCheckBox::indicator:disabled {{ background: {t.surface_alt}; border-color: {t.border}; }}
QGroupBox {{ border: 1px solid {t.border}; border-radius: 10px; margin-top: 14px;
    padding: 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}

#Banner[level="warn"] {{ background: {t.warning_soft}; border: 1px solid {t.warning};
    border-radius: 10px; }}
#Banner[level="over"] {{ background: {t.danger_soft}; border: 1px solid {t.danger};
    border-radius: 10px; }}
#KpiValue {{ font-size: 24px; font-weight: 600; letter-spacing: -0.5px; }}
#KpiLabel {{ color: {t.muted}; font-size: 12px; font-weight: 500; }}
#KpiValueSmall {{ font-size: 20px; font-weight: 600; letter-spacing: -0.4px; }}
#KpiNote {{ color: {t.faint}; font-size: 12px; }}
#IconChip {{ border-radius: 10px; background: {t.accent_soft}; }}
#IconChip[tone="success"] {{ background: {t.success_soft}; }}
#IconChip[tone="warning"] {{ background: {t.warning_soft}; }}
#IconChip[tone="danger"] {{ background: {t.danger_soft}; }}
#Pill {{ border-radius: 9px; padding: 1px 8px; font-size: 11px; font-weight: 600; }}
"""


def _icon(name: str) -> str:
    return (FONTS_DIR.parent / "icons" / f"{name}.svg").as_posix()


def _chevron(t: Tokens) -> str:
    return _icon(f"chevron-down-{t.name}")


def mono(base: QFont | None = None, delta: float = 0.0) -> QFont:
    """Geist Mono za iznose, datume i brojeve koji stoje u kolonama."""
    f = QFont(base) if base is not None else QFont()
    f.setFamily(MONO_FAMILY if MONO_FAMILY in QFontDatabase.families() else "Consolas")
    if delta:
        f.setPointSizeF(max(7.0, f.pointSizeF() + delta))
    return f


def repolish(widget) -> None:
    """Primeni stil ponovo posle promene dinamičkog svojstva (npr. setProperty('state', ...))."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
