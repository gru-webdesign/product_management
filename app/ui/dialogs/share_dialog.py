"""Dijalog „Podeli“: objava snimka projekta na link, PIN, automatsko ažuriranje, komentari."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.services import projects as project_service
from app.services import sharing
from app.share.client import ShareError
from app.share.snapshot import ShareOptions
from app.ui import icons, theme
from app.ui.context import AppContext
from app.ui.widgets.comments_panel import CommentsPanel


class ShareDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.project_id = ctx.project_id
        with ctx.session() as s:
            project = project_service.get(s, self.project_id)
            self.setWindowTitle(f"Podeli: {project.name}")
        self.setMinimumSize(620, 640)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        intro = QLabel(
            "Link prikazuje snimak stanja projekta samo za pregled. Gledaoci mogu da ostave "
            "komentar, a ne mogu ništa da menjaju. Beleške i opisi zadataka se ne dele."
        )
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        root.addWidget(intro)

        self.setup_box = QFrame()
        self.setup_box.setObjectName("Banner")
        self.setup_box.setProperty("level", "warn")
        sl = QHBoxLayout(self.setup_box)
        sl.setContentsMargins(14, 10, 14, 10)
        setup_text = QLabel(
            "Deljenje još nije podešeno. Potreban je besplatan Cloudflare "
            "Worker (podešava se jednom)."
        )
        setup_text.setWordWrap(True)
        sl.addWidget(setup_text, 1)
        setup = QPushButton("Podesi…")
        setup.clicked.connect(self._open_settings)
        sl.addWidget(setup)
        root.addWidget(self.setup_box)

        what = QGroupBox("Šta se vidi na linku")
        wl = QHBoxLayout(what)
        self.show_gantt = QCheckBox("Gant")
        self.show_list = QCheckBox("Lista zadataka")
        self.show_budget = QCheckBox("Budžet")
        self.show_budget.setToolTip(
            "Zbirovi po kategorijama; pojedinačni troškovi i dobavljači se ne prikazuju."
        )
        for w in (self.show_gantt, self.show_list, self.show_budget):
            wl.addWidget(w)
        wl.addStretch(1)
        root.addWidget(what)

        protect = QGroupBox("Zaštita i ažuriranje")
        pl = QVBoxLayout(protect)
        pin_row = QHBoxLayout()
        self.use_pin = QCheckBox("Traži PIN")
        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setMaxLength(32)
        self.pin.setPlaceholderText("4 do 32 znaka")
        self.use_pin.toggled.connect(self._pin_toggled)
        pin_row.addWidget(self.use_pin)
        pin_row.addWidget(self.pin, 1)
        pl.addLayout(pin_row)
        self.auto_update = QCheckBox(
            "Automatski ažuriraj link posle svake izmene (kad ima interneta)"
        )
        pl.addWidget(self.auto_update)
        root.addWidget(protect)

        link_row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setReadOnly(True)
        self.url.setPlaceholderText("Link još nije objavljen")
        self.copy_button = QPushButton("Kopiraj")
        self.copy_button.setIcon(icons.icon("link"))
        self.copy_button.clicked.connect(self._copy)
        self.open_button = QPushButton("Otvori")
        self.open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.url.text())) if self.url.text() else None
        )
        link_row.addWidget(self.url, 1)
        link_row.addWidget(self.copy_button)
        link_row.addWidget(self.open_button)
        root.addLayout(link_row)

        actions = QHBoxLayout()
        self.status = QLabel()
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        actions.addWidget(self.status, 1)
        self.revoke_button = QPushButton("Opozovi link")
        self.revoke_button.setProperty("danger", True)
        self.revoke_button.clicked.connect(self._revoke)
        self.publish_button = QPushButton("Objavi link")
        self.publish_button.setProperty("primary", True)
        self.publish_button.setIcon(icons.icon("share", theme.tokens().accent_text))
        self.publish_button.clicked.connect(self._publish)
        actions.addWidget(self.revoke_button)
        actions.addWidget(self.publish_button)
        root.addLayout(actions)

        comments_box = QGroupBox("Komentari gledalaca")
        cl = QVBoxLayout(comments_box)
        self.comments = CommentsPanel(ctx)
        cl.addWidget(self.comments)
        root.addWidget(comments_box, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close = QPushButton("Zatvori")
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        root.addLayout(close_row)
        self._load()

    # --- stanje ----------------------------------------------------------------------------------

    def _load(self) -> None:
        with self.ctx.session() as s:
            self.is_configured = sharing.configured(s)
            link = sharing.active_link(s, self.project_id)
            opts = sharing.options_of(link) if link else ShareOptions()
            self.has_pin = bool(link and link.pin_hash)
            published = bool(link and link.last_published_at)
            url = link.url if published else ""
            when = (
                link.last_published_at.astimezone().strftime("%d.%m.%Y. u %H:%M")
                if published
                else ""
            )
            auto = bool(link and link.auto_update)
        self.setup_box.setVisible(not self.is_configured)
        theme.repolish(self.setup_box)
        self.show_gantt.setChecked(opts.show_gantt)
        self.show_list.setChecked(opts.show_list)
        self.show_budget.setChecked(opts.show_budget)
        self.use_pin.setChecked(self.has_pin)
        self.pin.clear()
        self.pin.setPlaceholderText(
            "PIN je postavljen. Upiši novi da ga promeniš." if self.has_pin else "4 do 32 znaka"
        )
        self._pin_toggled(self.has_pin)
        self.auto_update.setChecked(auto)
        self.url.setText(url)
        self.copy_button.setEnabled(bool(url))
        self.open_button.setEnabled(bool(url))
        self.revoke_button.setEnabled(published)
        self.publish_button.setText("Ažuriraj link" if published else "Objavi link")
        self.publish_button.setEnabled(self.is_configured)
        self.status.setText(
            f"Poslednja objava: {when}" if published else "Link se pravi pri prvoj objavi."
        )

    def _pin_toggled(self, on: bool) -> None:
        self.pin.setEnabled(on)

    def _options(self) -> ShareOptions:
        return ShareOptions(
            self.show_gantt.isChecked(), self.show_list.isChecked(), self.show_budget.isChecked()
        )

    # --- akcije ----------------------------------------------------------------------------------

    def _publish(self) -> None:
        if self.use_pin.isChecked():
            typed = self.pin.text().strip()
            if not typed and not self.has_pin:
                self.status.setText("Upiši PIN ili isključi „Traži PIN“.")
                return
            pin = typed or None  # prazno = zadrži postojeći
        else:
            pin = ""
        options, auto = self._options(), self.auto_update.isChecked()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with self.ctx.session() as s:
                with sharing.make_client(s) as client:
                    link = sharing.publish(s, client, self.project_id, options, pin, auto)
                s.commit()
                url = link.url
        except (ShareError, ValueError) as exc:
            QApplication.restoreOverrideCursor()
            self.status.setText(str(exc))
            return
        QApplication.restoreOverrideCursor()
        self._load()
        QGuiApplication.clipboard().setText(url)
        self.status.setText(
            "Objavljeno. Link je kopiran, pošalji ga klijentu"
            + (" zajedno sa PIN-om." if self.use_pin.isChecked() else ".")
        )
        self.ctx.notify("Link za deljenje je objavljen.")

    def _revoke(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Opozovi link",
                "Link će prestati da radi za sve koji ga imaju, a komentari na njemu se brišu sa "
                "servera (preuzeti komentari ostaju u aplikaciji). Nastaviti?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with self.ctx.session() as s:
                link = sharing.active_link(s, self.project_id)
                with sharing.make_client(s) as client:
                    sharing.sync_comments(s, client, link)
                    sharing.revoke(s, client, link)
                s.commit()
        except ShareError as exc:
            self.status.setText(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._load()
        self.comments.reload()
        self.status.setText("Link je opozvan. Sledeća objava pravi novi link.")

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.url.text())
        self.status.setText("Link je kopiran.")

    def _open_settings(self) -> None:
        from app.ui.dialogs.settings_dialog import SettingsDialog

        SettingsDialog(self.ctx, self, tab="share").exec()
        self._load()
