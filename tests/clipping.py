"""Pronalazi isečen tekst: labele, dugmad i polja koja su manja nego što njihov tekst traži.

Koristi se u test_ui_clipping.py i u skripti za snimke; radi nad bilo kojim prozorom.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabBar,
    QTextEdit,
    QToolButton,
    QWidget,
)

TOL = 1  # piksel tolerancije za zaokruživanje


def _name(w: QWidget) -> str:
    text = ""
    for attr in ("text", "placeholderText", "currentText"):
        fn = getattr(w, attr, None)
        if callable(fn):
            try:
                text = fn()
            except TypeError:
                continue
            if text:
                break
    owner = w.window().windowTitle() or type(w.window()).__name__
    return f"{owner} › {type(w).__name__} {w.objectName()!r} „{str(text)[:50]}“"


def _visible(w: QWidget) -> bool:
    return w.isVisible() and w.width() > 0 and w.height() > 0


def find_clipped(root: QWidget) -> list[str]:
    problems: list[str] = []
    for w in [root, *root.findChildren(QWidget)]:
        if not _visible(w):
            continue
        if isinstance(w, QTabBar) and w.count():
            need = sum(w.tabSizeHint(i).width() for i in range(w.count()))
            if w.width() + TOL < need and not w.parentWidget().objectName() == "ViewTabs":
                problems.append(f"{_name(w)}: tabovi ne staju ({w.width()} < {need})")
            continue
        if isinstance(w, QLabel) and w.text():
            if w.wordWrap():
                need = w.heightForWidth(w.width())
                if need > 0 and w.height() + TOL < need:
                    problems.append(f"{_name(w)}: visina {w.height()} < {need}")
            elif w.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Ignored:
                hint = w.minimumSizeHint()
                if w.width() + TOL < hint.width():
                    problems.append(f"{_name(w)}: širina {w.width()} < {hint.width()}")
                if w.height() + TOL < hint.height():
                    problems.append(f"{_name(w)}: visina {w.height()} < {hint.height()}")
        elif isinstance(w, QPushButton | QCheckBox) or (
            isinstance(w, QToolButton) and w.text() and not w.autoRaise()
        ):
            hint = w.sizeHint()
            if isinstance(w, QAbstractButton) and w.text() and w.width() + TOL < hint.width():
                problems.append(f"{_name(w)}: širina {w.width()} < {hint.width()}")
            if w.height() + TOL < w.minimumSizeHint().height():
                problems.append(f"{_name(w)}: visina {w.height()} < {w.minimumSizeHint().height()}")
        elif isinstance(w, QLineEdit | QComboBox) and not isinstance(
            w.parentWidget(), QComboBox | QAbstractSpinBox
        ):
            need = w.fontMetrics().height() + 4
            if w.height() < need:
                problems.append(f"{_name(w)}: visina {w.height()} < {need}")
        elif isinstance(w, QPlainTextEdit | QTextEdit) and not w.isReadOnly():
            need = int(w.fontMetrics().lineSpacing() * 2.5)
            if w.height() < need:
                problems.append(f"{_name(w)}: visina {w.height()} < {need} (manje od 2 reda)")
    return problems
