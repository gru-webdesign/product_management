"""Podešavanja: opšte (ime, valuta, satnica, prag upozorenja, tema) i deljenje (Worker)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select

from app.db.models import CostEntry, IncomeEntry
from app.services import sharing
from app.services.defaults import get_setting, set_setting
from app.services.money import SUPPORTED_CURRENCIES
from app.share.client import ShareClient, ShareError
from app.share.secrets import get_admin_key, uses_fallback
from app.ui import theme
from app.ui.context import AppContext
from app.ui.widgets.fields import MoneyEdit

WORKER_HELP = "https://github.com/gru-webdesign/product_management/blob/main/share_worker/README.md"


class SettingsDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None, tab: str = "general") -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Podešavanja")
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._general(), "Opšte")
        self.tabs.addTab(self._share(), "Deljenje")
        self.tabs.setCurrentIndex(1 if tab == "share" else 0)
        root.addWidget(self.tabs)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color: {theme.tokens().danger};")
        self.error.hide()
        root.addWidget(self.error)
        buttons = QDialogButtonBox()
        save = buttons.addButton("Sačuvaj", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setProperty("primary", True)
        save.setDefault(True)
        buttons.addButton("Otkaži", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _form(self) -> tuple[QWidget, QFormLayout]:
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(4, 14, 4, 4)
        f.setHorizontalSpacing(14)
        f.setVerticalSpacing(10)
        return w, f

    def _general(self) -> QWidget:
        w, f = self._form()
        with self.ctx.session() as s:
            name = get_setting(s, "user_name")
            base = get_setting(s, "base_currency") or "RSD"
            rate = int(get_setting(s, "default_hourly_rate_minor") or 0)
            warn = int(get_setting(s, "budget_warn_percent") or 80)
            mode = get_setting(s, "theme") or "system"
            entries = (s.scalar(select(func.count(CostEntry.id))) or 0) + (
                s.scalar(select(func.count(IncomeEntry.id))) or 0
            )
        self.user_name = QLineEdit(name)
        self.user_name.setPlaceholderText("prikazuje se u izveštajima")
        self.base = QComboBox()
        for c in SUPPORTED_CURRENCIES:
            self.base.addItem(c, c)
        self.base.setCurrentIndex(max(0, self.base.findData(base)))
        if entries:
            self.base.setEnabled(False)
            self.base.setToolTip(
                "Osnovna valuta ne može da se menja kad već postoje troškovi "
                "ili prihodi (zbirovi bi postali netačni)."
            )
        self.rate = MoneyEdit(rate)
        self.rate.setPlaceholderText("npr. 2.500,00")
        self.warn = QSpinBox()
        self.warn.setRange(10, 100)
        self.warn.setSuffix(" %")
        self.warn.setValue(warn)
        self.theme = QComboBox()
        for key, label in (("system", "Kao sistem"), ("light", "Svetla"), ("dark", "Tamna")):
            self.theme.addItem(label, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(mode)))
        f.addRow("Tvoje ime", self.user_name)
        f.addRow("Osnovna valuta", self.base)
        f.addRow("Satnica", self.rate)
        f.addRow("Upozorenje budžeta", self.warn)
        f.addRow("Tema", self.theme)
        hint = QLabel(
            "Satnica se koristi za procenu vrednosti rada (utrošeni sati × satnica) "
            "u pregledu budžeta."
        )
        hint.setWordWrap(True)
        hint.setProperty("faint", True)
        f.addRow("", hint)
        return w

    def _share(self) -> QWidget:
        w, f = self._form()
        with self.ctx.session() as s:
            url = sharing.worker_url(s)
            has_key = bool(get_admin_key(s))
            fallback = uses_fallback(s)
        intro = QLabel(
            "Deljenje koristi tvoj besplatni Cloudflare Worker. Napravi ga jednom po uputstvu, "
            "pa ovde upiši njegovu adresu i tajni ključ."
        )
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        f.addRow(intro)
        help_button = QPushButton("Uputstvo za postavljanje Worker-a →")
        help_button.setProperty("link", True)
        help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        help_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(WORKER_HELP)))
        f.addRow("", help_button)
        self.worker_url = QLineEdit(url)
        self.worker_url.setPlaceholderText("https://etapa-share.tvojnalog.workers.dev")
        self.admin_key = QLineEdit()
        self.admin_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_key.setPlaceholderText(
            "sačuvan — upiši novi da ga promeniš" if has_key else "ADMIN_KEY iz uputstva"
        )
        f.addRow("Adresa Worker-a", self.worker_url)
        f.addRow("Tajni ključ", self.admin_key)
        row = QHBoxLayout()
        test = QPushButton("Proveri vezu")
        test.clicked.connect(self._test)
        row.addWidget(test)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        row.addWidget(self.test_result, 1)
        f.addRow("", row)
        if fallback:
            warn = QLabel(
                "Sistemsko skladište lozinki nije dostupno, pa je ključ sačuvan u lokalnoj bazi."
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {theme.tokens().warning};")
            f.addRow("", warn)
        return w

    def _test(self) -> None:
        t = theme.tokens()
        with self.ctx.session() as s:
            key = self.admin_key.text().strip() or get_admin_key(s)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with ShareClient(self.worker_url.text(), key) as client:
                version = client.ping()
            self.test_result.setText(f"Veza radi (Worker v{version}).")
            self.test_result.setStyleSheet(f"color: {t.success};")
        except ShareError as exc:
            self.test_result.setText(str(exc))
            self.test_result.setStyleSheet(f"color: {t.danger};")
        finally:
            QApplication.restoreOverrideCursor()

    def _save(self) -> None:
        if not self.rate.is_valid():
            self._fail("Satnica nije ispravan iznos.")
            return
        values = {
            "user_name": self.user_name.text().strip(),
            "default_hourly_rate_minor": str(self.rate.value_minor()),
            "budget_warn_percent": str(self.warn.value()),
            "theme": self.theme.currentData(),
        }
        if self.base.isEnabled():
            values["base_currency"] = self.base.currentData()
        url = self.worker_url.text().strip()
        key = self.admin_key.text().strip() or None

        def work(s):
            for k, v in values.items():
                set_setting(s, k, v)
            try:
                sharing.save_config(s, url, key)
            except ShareError as exc:
                raise ValueError(str(exc)) from exc
            return True

        if self.ctx.run(work, self):
            theme.apply(QApplication.instance(), values["theme"])
            self.accept()

    def _fail(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()
