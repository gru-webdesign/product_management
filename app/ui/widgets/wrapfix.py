"""Prelomljen tekst (QLabel sa wordWrap) nikad ne sme da bude isečen.

Qt raspored ne pita labelu koliko joj visine treba za datu širinu kada je widget poravnat
(AlignCenter) ili kada je u kartici fiksne širine; tada dobije visinu iz sizeHint-a koja je
računata za drugu širinu i font, pa se donji i gornji red iseku (vidljivo na Windows-u sa
uvećanim fontom). Ovaj filter posle svake promene veličine, fonta ili stila postavi labeli
minimalnu visinu tačno koliko tekst traži za njenu stvarnu širinu.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QDialog, QLabel

_EVENTS = {
    QEvent.Type.Resize,
    QEvent.Type.Show,
    QEvent.Type.FontChange,
    QEvent.Type.StyleChange,
    QEvent.Type.Polish,
}


def fit(label: QLabel) -> None:
    if not label.wordWrap() or not label.text():
        return
    width = label.width() if label.width() > 0 else label.sizeHint().width()
    need = label.heightForWidth(width)
    if need > 0 and label.minimumHeight() != need:
        label.setMinimumHeight(need)


class _WrapFix(QObject):
    """Filter samo na labelama sa prelomom (ne na celoj aplikaciji, da ne troši CPU)."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() in _EVENTS and isinstance(obj, QLabel):
            fit(obj)
        return False


_filter: _WrapFix | None = None


def install(app: QApplication) -> None:
    """Uključuje popravke: prelomljene labele i veličinu dijaloga pri prikazu."""
    global _filter
    if _filter is not None:
        return
    _filter = _WrapFix(app)

    orig_set_wrap = QLabel.setWordWrap
    orig_set_text = QLabel.setText
    orig_show = QDialog.showEvent

    def set_word_wrap(self: QLabel, on: bool) -> None:
        orig_set_wrap(self, on)
        if on:
            self.installEventFilter(_filter)
            fit(self)
        else:
            self.removeEventFilter(_filter)

    def set_text(self: QLabel, text) -> None:
        # setText ne šalje Resize ako se širina ne menja; zato i on poziva fit
        orig_set_text(self, text)
        if self.wordWrap():
            fit(self)

    def show_event(self: QDialog, event) -> None:
        orig_show(self, event)
        from app.ui.dialogs.base import fit_to_content

        fit_to_content(self)

    QLabel.setWordWrap = set_word_wrap
    QLabel.setText = set_text
    QDialog.showEvent = show_event
