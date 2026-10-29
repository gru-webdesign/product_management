"""Glavni prozor: sidebar sa projektima levo, zaglavlje projekta i tabovi prikaza desno."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, __version__
from app.db.base import Database
from app.labels import PROJECT_STATUS
from app.services import projects as project_service
from app.services.defaults import get_setting
from app.ui import icons, theme
from app.ui.context import AppContext
from app.ui.sidebar import Sidebar
from app.ui.views.base import ProjectView


def _fmt(d) -> str:
    return d.strftime("%d.%m.%Y.") if d else "?"


class EmptyState(QWidget):
    def __init__(self, on_create, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        title = QLabel("Još nema projekata")
        title.setObjectName("EmptyTitle")
        text = QLabel("Napravi prvi projekat, pa dodaj zadatke, rokove i budžet.")
        text.setObjectName("EmptyText")
        button = QPushButton("Novi projekat")
        button.setProperty("primary", True)
        button.setIcon(icons.icon("plus", theme.tokens().accent_text))
        button.clicked.connect(on_create)
        for w in (title, text):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(w)
        lay.addSpacing(10)
        lay.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(2)


class ProjectHeader(QFrame):
    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Header")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 14, 20, 10)
        lay.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(6)
        self.title = QLabel()
        self.title.setObjectName("ProjectTitle")
        text.addWidget(self.title)
        meta = QHBoxLayout()
        meta.setSpacing(18)
        self.client = QLabel()
        self.client.setProperty("muted", True)
        self.status = QLabel()
        self.status.setObjectName("StatusChip")
        self.dates = QLabel()
        self.dates.setProperty("muted", True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedSize(90, 6)
        self.progress_bar.setTextVisible(False)
        self.progress_text = QLabel()
        self.progress_text.setProperty("muted", True)
        progress = QHBoxLayout()
        progress.setSpacing(8)
        progress.addWidget(self.progress_bar)
        progress.addWidget(self.progress_text)
        for w in (self.client, self.status, self.dates):
            meta.addWidget(w)
        meta.addLayout(progress)
        meta.addStretch(1)
        text.addLayout(meta)
        lay.addLayout(text, 1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Pretraži zadatke (Ctrl+F)")
        self.search.addAction(icons.icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        self._debounce = QTimer(self, singleShot=True, interval=200)
        self._debounce.timeout.connect(lambda: ctx.set_search(self.search.text()))
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        lay.addWidget(self.search)

        self.share_button = QPushButton("Podeli")
        self.share_button.setIcon(icons.icon("share"))
        lay.addWidget(self.share_button)

        self.add_task_button = QPushButton("Zadatak")
        self.add_task_button.setProperty("primary", True)
        self.add_task_button.setIcon(icons.icon("plus", theme.tokens().accent_text))
        self.add_task_button.setToolTip("Novi zadatak (Ctrl+N)")
        lay.addWidget(self.add_task_button)

    def reload(self) -> None:
        pid = self.ctx.project_id
        if not pid:
            return
        with self.ctx.session() as s:
            p = project_service.get(s, pid)
            if p is None:
                return
            done, total, pct = project_service.progress(s, pid)
            self.title.setText(p.name)
            self.client.setText(p.client)
            self.client.setVisible(bool(p.client))
            self.status.setText("Arhiviran" if p.archived else PROJECT_STATUS[p.status])
            has_dates = bool(p.start_date or p.end_date)
            self.dates.setText(f"{_fmt(p.start_date)} - {_fmt(p.end_date)}" if has_dates else "")
            self.dates.setVisible(has_dates)
            self.progress_bar.setValue(pct)
            self.progress_text.setText(f"{done} od {total} zadataka završeno, {pct}%")

    def meta_text(self) -> str:
        return "  ".join(
            w.text() for w in (self.client, self.status, self.dates, self.progress_text) if w.text()
        )


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self.ctx = AppContext(db)
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 840)
        self.setMinimumSize(1024, 640)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        with db.session() as s:
            last = get_setting(s, "last_project_id")
            if last and project_service.get(s, last) is not None:
                self.ctx.project_id = last
        self.sidebar = Sidebar(self.ctx)
        self.sidebar.settings_requested.connect(self.open_settings)
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.empty = EmptyState(self.sidebar.new_project)
        self.stack.addWidget(self.empty)

        project_page = QWidget()
        page = QVBoxLayout(project_page)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        self.header = ProjectHeader(self.ctx)
        self.header.add_task_button.clicked.connect(self.new_task)
        self.header.share_button.clicked.connect(self.open_share)
        page.addWidget(self.header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.views: list[ProjectView] = self._make_views()
        for view in self.views:
            self.tabs.addTab(view, icons.icon(view.icon_name), view.title)
        tabs_wrap = QWidget()
        tw = QVBoxLayout(tabs_wrap)
        tw.setContentsMargins(16, 4, 16, 12)
        tw.addWidget(self.tabs)
        page.addWidget(tabs_wrap, 1)
        self.stack.addWidget(project_page)
        from app.ui.views.dashboard_view import DashboardView

        self.dashboard = DashboardView(self.ctx)
        self.stack.addWidget(self.dashboard)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage(f"Baza: {db.paths.db_path}")
        from app.ui.widgets.timer_widget import TimerWidget

        self.timer_widget = TimerWidget(self.ctx)
        self.statusBar().addPermanentWidget(self.timer_widget)
        self.ctx.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.ctx.project_changed.connect(self._project_changed)
        self.ctx.show_dashboard.connect(lambda: self.stack.setCurrentWidget(self.dashboard))
        self.ctx.data_changed.connect(self.header.reload)
        self.ctx.open_task_requested.connect(self.open_task)
        theme.manager().changed.connect(self._theme_changed)

        self._make_menu()
        self._project_changed(self.ctx.project_id)

        # deljenje: broj novih komentara na dugmetu, automatsko ažuriranje linka posle izmena
        self._auto_timer = QTimer(self, singleShot=True, interval=6000)
        self._auto_timer.timeout.connect(self._auto_publish)
        self.ctx.data_changed.connect(self._update_share_badge)
        self.ctx.data_changed.connect(self._schedule_auto_publish)
        self.ctx.project_changed.connect(lambda _p: self._update_share_badge())
        self._update_share_badge()
        self._restore_window()

        from PySide6.QtGui import QIcon

        from app.ui.reminders import ReminderManager

        icon_path = Path(__file__).resolve().parents[1] / "resources" / "icons" / "app.png"
        self.setWindowIcon(QIcon(str(icon_path)))
        self.reminders = ReminderManager(self.ctx, self, self.windowIcon())

    # --- sastavljanje ----------------------------------------------------------------------------

    def _make_views(self) -> list[ProjectView]:
        from app.ui.views.budget_view import BudgetView
        from app.ui.views.gantt.gantt_view import GanttView
        from app.ui.views.kanban_view import KanbanView
        from app.ui.views.list_view import ListView

        views: list[ProjectView] = []
        for cls, title, icon_name in (
            (ListView, "Lista", "list"),
            (KanbanView, "Kanban", "kanban"),
            (GanttView, "Gant", "gantt"),
            (BudgetView, "Budžet", "wallet"),
        ):
            view = cls(self.ctx)
            view.title, view.icon_name = title, icon_name
            views.append(view)
        return views

    def _make_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Datoteka")
        self._action(file_menu, "Novi projekat", "Ctrl+Shift+N", self.sidebar.new_project)
        self._action(file_menu, "Novi zadatak", "Ctrl+N", self.new_task)
        file_menu.addSeparator()
        export_menu = file_menu.addMenu(icons.icon("download"), "Izvezi")
        self._action(export_menu, "PDF izveštaj…", "Ctrl+P", self.export_pdf)
        self._action(export_menu, "Projekat u Excel…", "Ctrl+Shift+X", self.export_xlsx)
        self._action(export_menu, "Zadaci ili troškovi u CSV…", "Ctrl+E", self.export_csv)
        self._action(file_menu, "Otvori folder sa podacima", None, self.open_data_folder)
        self._action(file_menu, "Vrati bazu iz kopije…", None, self.restore_backup)
        file_menu.addSeparator()
        self._action(file_menu, "Podešavanja…", "Ctrl+,", self.open_settings)
        self._action(file_menu, "Izlaz", "Ctrl+Q", self.close)

        project_menu = bar.addMenu("&Projekat")
        self._action(project_menu, "Uredi projekat…", "Ctrl+Shift+E", self.sidebar.edit_current)
        self._action(project_menu, "Arhiviraj / vrati", None, self.sidebar.toggle_archive_current)
        self._action(project_menu, "Podeli linkom…", "Ctrl+Shift+S", self.open_share)
        project_menu.addSeparator()
        self._action(project_menu, "Sačuvaj kao šablon…", None, self.save_template)
        self._action(project_menu, "Šabloni projekata…", None, self.manage_templates)
        project_menu.addSeparator()
        self._action(project_menu, "Obriši projekat…", None, self.sidebar.delete_current)

        view_menu = bar.addMenu("&Prikaz")
        self._action(view_menu, "Pregled svih projekata", "Ctrl+0", self.ctx.show_dashboard.emit)
        for i, view in enumerate(self.views):
            self._action(
                view_menu, view.title, f"Ctrl+{i + 1}", lambda i=i: self.tabs.setCurrentIndex(i)
            )
        view_menu.addSeparator()
        self._action(view_menu, "Pretraga", "Ctrl+F", self.focus_search)
        theme_menu = view_menu.addMenu("Tema")
        for mode, label in (("system", "Kao sistem"), ("light", "Svetla"), ("dark", "Tamna")):
            self._action(theme_menu, label, None, lambda m=mode: self.set_theme(m))

        help_menu = bar.addMenu("Po&moć")
        self._action(help_menu, "Prečice na tastaturi", "F1", self.shortcuts)
        self._action(
            help_menu, "Proveri rokove sada", None, lambda: self.reminders.check(force=True)
        )
        self._action(help_menu, f"O programu {APP_NAME}", None, self.about)

    def _action(self, menu, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _c=False: slot())
        menu.addAction(action)
        self.addAction(action)
        return action

    # --- stanje ----------------------------------------------------------------------------------

    def _project_changed(self, pid: str) -> None:
        if self.sidebar.dashboard_mode and pid:
            self.sidebar.select(pid)
        if self.sidebar.dashboard_mode:
            return
        self.stack.setCurrentIndex(1 if pid else 0)
        self.header.reload()

    def _theme_changed(self) -> None:
        for i, view in enumerate(self.views):
            self.tabs.setTabIcon(i, icons.icon(view.icon_name))
        self.ctx.data_changed.emit()

    def current_view(self) -> ProjectView:
        return self.views[self.tabs.currentIndex()]

    # --- pamćenje stanja prozora ----------------------------------------------------------------

    def _restore_window(self) -> None:
        import os

        from PySide6.QtCore import QSettings

        if os.environ.get("ETAPA_TEST"):
            return
        qs = QSettings(APP_NAME, APP_NAME)
        geometry = qs.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        tab = qs.value("window/tab", 0)
        try:
            self.tabs.setCurrentIndex(int(tab))
        except (TypeError, ValueError):
            pass

    def closeEvent(self, event) -> None:
        from PySide6.QtCore import QSettings

        from app.services.defaults import set_setting

        qs = QSettings(APP_NAME, APP_NAME)
        qs.setValue("window/geometry", self.saveGeometry())
        qs.setValue("window/tab", self.tabs.currentIndex())
        pid = self.ctx.project_id
        with self.db.session() as s:
            set_setting(s, "last_project_id", pid)
            s.commit()
        self.reminders.shutdown()
        super().closeEvent(event)

    def shortcuts(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        rows = [
            ("Ctrl+N", "Novi zadatak"),
            ("Ctrl+Shift+N", "Novi projekat"),
            ("Ctrl+F", "Pretraga"),
            ("Ctrl+1 do Ctrl+4", "Lista, Kanban, Gant, Budžet"),
            ("F2 / Enter", "Otvori izabrani zadatak (Lista)"),
            ("Delete", "Obriši izabrano (Lista, zavisnost na Gantu)"),
            ("Ctrl+točkić", "Zum na Gantu"),
            ("Shift+točkić", "Skrol levo-desno na Gantu"),
            ("Ctrl+0", "Pregled svih projekata"),
            ("Ctrl+P", "PDF izveštaj"),
            ("Ctrl+Shift+X", "Izvoz u Excel"),
            ("Ctrl+E", "Izvoz u CSV"),
            ("Ctrl+Shift+S", "Podeli linkom"),
            ("Ctrl+,", "Podešavanja"),
            ("Ctrl+Q", "Izlaz"),
        ]
        html = (
            "<table cellpadding='4'>"
            + "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows)
            + "</table>"
        )
        QMessageBox.information(self, "Prečice na tastaturi", html)

    # --- akcije ----------------------------------------------------------------------------------

    def focus_search(self) -> None:
        self.header.search.setFocus()
        self.header.search.selectAll()

    def new_task(self) -> None:
        if not self.ctx.project_id:
            return
        from app.ui.dialogs.task_dialog import open_new_task

        open_new_task(self.ctx, self)

    def open_task(self, task_id: str) -> None:
        from app.ui.dialogs.task_dialog import open_task

        open_task(self.ctx, task_id, self)

    def save_template(self) -> None:
        from app.ui.dialogs.templates_dialog import save_current_as_template

        save_current_as_template(self.ctx, self)

    def manage_templates(self) -> None:
        from app.ui.dialogs.templates_dialog import TemplatesDialog

        TemplatesDialog(self.ctx, self).exec()

    def open_share(self) -> None:
        if not self.ctx.project_id:
            return
        from app.ui.dialogs.share_dialog import ShareDialog

        ShareDialog(self.ctx, self).exec()
        self._update_share_badge()

    def open_settings(self) -> None:
        from app.ui.dialogs.settings_dialog import SettingsDialog

        SettingsDialog(self.ctx, self).exec()

    def export_csv(self) -> None:
        from app.ui.export import export_tasks_dialog

        export_tasks_dialog(self.ctx, self)

    def export_xlsx(self) -> None:
        from app.ui.export import export_xlsx_dialog

        export_xlsx_dialog(self.ctx, self)

    def export_pdf(self) -> None:
        from app.ui.export import export_pdf_dialog

        export_pdf_dialog(self.ctx, self)

    # --- deljenje u pozadini ---------------------------------------------------------------------

    def _update_share_badge(self) -> None:
        pid = self.ctx.project_id
        if not pid:
            return
        from app.services import sharing

        with self.ctx.session() as s:
            n = sharing.unread_count(s, pid)
            link = sharing.active_link(s, pid)
            shared = bool(link and link.last_published_at)
        text = "Podeli"
        if n:
            word = "novi komentar" if n == 1 else ("nova komentara" if n < 5 else "novih komentara")
            text = f"Podeli · {n} {word}"
        self.header.share_button.setText(text)
        self.header.share_button.setToolTip(
            "Projekat je podeljen linkom" if shared else "Podeli projekat linkom za pregled"
        )

    def _schedule_auto_publish(self) -> None:
        self._auto_timer.start()

    def _auto_publish(self) -> None:
        pid = self.ctx.project_id
        if not pid:
            return
        from app.services import sharing

        with self.ctx.session() as s:
            link = sharing.active_link(s, pid)
            if not (link and link.auto_update and link.last_published_at and sharing.configured(s)):
                return

        def work(s):
            with sharing.make_client(s) as client:
                sharing.publish(s, client, pid)

        from app.ui import background

        background.run(
            self.db,
            work,
            lambda _r: self.ctx.notify("Link za deljenje je ažuriran."),
            lambda err: self.ctx.notify(f"Link nije ažuriran: {err}"),
        )

    def sync_comments_in_background(self) -> None:
        from app.services import sharing
        from app.ui import background

        with self.ctx.session() as s:
            if not sharing.configured(s):
                return

        def work(s):
            with sharing.make_client(s) as client:
                return sharing.sync_all(s, client)

        def done(n):
            if n:
                self.ctx.notify(f"Stiglo je novih komentara sa linka: {n}.")
                self.ctx.data_changed.emit()

        background.run(self.db, work, done, lambda _e: None)

    def open_data_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.db.paths.data_dir)))

    def restore_backup(self) -> None:
        from app.ui.dialogs.restore_dialog import RestoreDialog

        RestoreDialog(self.ctx, self).exec()

    def set_theme(self, mode: str) -> None:
        theme.apply(QApplication.instance(), mode)
        from app.services.defaults import set_setting

        self.ctx.run(lambda s: set_setting(s, "theme", mode))

    def about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            f"O programu {APP_NAME}",
            f"<b>{APP_NAME}</b> v{__version__}<br><br>"
            "Upravljanje projektima, rokovima i budžetom.<br>"
            "Svi podaci su lokalno na ovom računaru.<br><br>"
            f"Podaci: {self.db.paths.data_dir}",
        )


def initial_theme(db: Database) -> str:
    with db.session() as s:
        return get_setting(s, "theme") or "system"
