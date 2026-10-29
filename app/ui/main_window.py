"""Glavni prozor: sidebar sa projektima levo, zaglavlje projekta i tabovi prikaza desno."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
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
from app.ui.views.base import PlaceholderView, ProjectView


def _fmt(d) -> str:
    return d.strftime("%d.%m.%Y.") if d else "—"


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
        button.setIcon(icons.icon("plus", "#FFFFFF"))
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
        text.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("ProjectTitle")
        self.meta = QLabel()
        self.meta.setObjectName("ProjectMeta")
        text.addWidget(self.title)
        text.addWidget(self.meta)
        lay.addLayout(text, 1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Pretraži zadatke…  (Ctrl+F)")
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
        self.add_task_button.setIcon(icons.icon("plus", "#FFFFFF"))
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
            parts = []
            if p.client:
                parts.append(p.client)
            parts.append(PROJECT_STATUS[p.status])
            if p.start_date or p.end_date:
                parts.append(f"{_fmt(p.start_date)} – {_fmt(p.end_date)}")
            parts.append(f"{done}/{total} zadataka · {pct}%")
            if p.archived:
                parts.append("arhiviran")
            self.title.setText(p.name)
            self.meta.setText("   ·   ".join(parts))


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
        self.views: list[ProjectView] = self._make_views()
        for view in self.views:
            self.tabs.addTab(view, icons.icon(view.icon_name), view.title)
        tabs_wrap = QWidget()
        tw = QVBoxLayout(tabs_wrap)
        tw.setContentsMargins(16, 4, 16, 12)
        tw.addWidget(self.tabs)
        page.addWidget(tabs_wrap, 1)
        self.stack.addWidget(project_page)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage(f"Baza: {db.paths.db_path}   ·   v{__version__}")
        self.ctx.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.ctx.project_changed.connect(self._project_changed)
        self.ctx.data_changed.connect(self.header.reload)
        self.ctx.open_task_requested.connect(self.open_task)
        theme.manager().changed.connect(self._theme_changed)

        self._make_menu()
        self._project_changed(self.ctx.project_id)

    # --- sastavljanje ----------------------------------------------------------------------------

    def _make_views(self) -> list[ProjectView]:
        views: list[ProjectView] = []
        builders = [
            ("app.ui.views.list_view", "ListView", "Lista", "list"),
            ("app.ui.views.kanban_view", "KanbanView", "Kanban", "kanban"),
            ("app.ui.views.gantt.gantt_view", "GanttView", "Gant", "gantt"),
            ("app.ui.views.budget_view", "BudgetView", "Budžet", "wallet"),
        ]
        import importlib

        for module, cls, title, icon_name in builders:
            try:
                view = getattr(importlib.import_module(module), cls)(self.ctx)
            except ModuleNotFoundError:
                view = PlaceholderView(self.ctx, title)
            view.title, view.icon_name = title, icon_name
            views.append(view)
        return views

    def _make_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&Datoteka")
        self._action(file_menu, "Novi projekat", "Ctrl+Shift+N", self.sidebar.new_project)
        self._action(file_menu, "Novi zadatak", "Ctrl+N", self.new_task)
        file_menu.addSeparator()
        self._action(file_menu, "Izvezi zadatke u CSV…", "Ctrl+E", self.export_csv)
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
        self._action(project_menu, "Obriši projekat…", None, self.sidebar.delete_current)

        view_menu = bar.addMenu("&Prikaz")
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
        self.stack.setCurrentIndex(1 if pid else 0)
        self.header.reload()

    def _theme_changed(self) -> None:
        for i, view in enumerate(self.views):
            self.tabs.setTabIcon(i, icons.icon(view.icon_name))
        self.ctx.data_changed.emit()

    def current_view(self) -> ProjectView:
        return self.views[self.tabs.currentIndex()]

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

    def open_share(self) -> None:
        if not self.ctx.project_id:
            return
        try:
            from app.ui.dialogs.share_dialog import ShareDialog
        except ModuleNotFoundError:
            self.ctx.notify("Deljenje linkom stiže u Koraku 12.")
            return
        ShareDialog(self.ctx, self).exec()

    def open_settings(self) -> None:
        try:
            from app.ui.dialogs.settings_dialog import SettingsDialog
        except ModuleNotFoundError:
            return
        SettingsDialog(self.ctx, self).exec()

    def export_csv(self) -> None:
        try:
            from app.ui.export import export_tasks_dialog
        except ModuleNotFoundError:
            return
        export_tasks_dialog(self.ctx, self)

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
