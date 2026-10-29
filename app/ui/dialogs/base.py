"""Osnova za dijaloge: dugmad Sačuvaj/Otkaži i prikaz greške validacije u samom dijalogu."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme


class FormDialog(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None, save_text: str = "Sačuvaj"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 16)
        self.root.setSpacing(12)

        self.form = QFormLayout()
        self.form.setHorizontalSpacing(14)
        self.form.setVerticalSpacing(10)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.root.addLayout(self.form)

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color: {theme.tokens().danger};")
        self.error.hide()
        self.root.addWidget(self.error)

        self.buttons = QDialogButtonBox()
        self.save_button = self.buttons.addButton(save_text, QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_button.setProperty("primary", True)
        self.save_button.setDefault(True)
        self.buttons.addButton("Otkaži", QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self._try_accept)
        self.buttons.rejected.connect(self.reject)
        self.root.addWidget(self.buttons)

    def validate(self) -> None:
        """Podklasa baca ValueError sa porukom ako forma nije ispravna."""

    def _try_accept(self) -> None:
        try:
            self.validate()
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.accept()

    def show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()
