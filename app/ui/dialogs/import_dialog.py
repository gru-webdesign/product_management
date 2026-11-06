"""Uvoz zadataka iz Excel/CSV tabele: izbor fajla, pregled pre uvoza, upis."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app import labels
from app.services import importer
from app.services import projects as project_service
from app.ui import icons, theme
from app.ui.context import AppContext
from app.ui.widgets.fields import SuggestCombo

COLUMNS = [
    "Red",
    "Projekat",
    "Zadatak",
    "Deo zadatka",
    "Status",
    "Nosilac",
    "Početak",
    "Rok",
    "Napomena",
]


class ImportDialog(QDialog):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Uvoz zadataka iz Excel-a")
        self.resize(1100, 680)
        self.table: list[list] | None = None
        self.plan: importer.Plan | None = None
        self.result: importer.Result | None = None

        root = QVBoxLayout(self)
        root.setSpacing(12)
        intro = QLabel(
            "Prva vrsta tabele su nazivi kolona (Projekat, Zadatak, Status, Nosilac, Početak, "
            "Rok...). Redosled nije bitan, a kolone se prepoznaju i pod drugim nazivima. "
            "Pre upisa vidiš šta će biti uvezeno."
        )
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        root.addWidget(intro)

        top = QHBoxLayout()
        pick = QPushButton("Izaberi fajl…")
        pick.setIcon(icons.icon("upload"))
        pick.setProperty("primary", True)
        pick.clicked.connect(self.pick_file)
        template = QPushButton("Preuzmi šablon za uvoz")
        template.setIcon(icons.icon("download"))
        template.clicked.connect(self.save_template)
        self.file_label = QLabel("Fajl nije izabran")
        self.file_label.setProperty("faint", True)
        top.addWidget(pick)
        top.addWidget(self.file_label, 1)
        top.addWidget(template)
        root.addLayout(top)

        form = QFormLayout()
        with ctx.session() as s:
            names = [p.name for p in project_service.list_projects(s)]
            current = project_service.get(s, ctx.project_id).name if ctx.project_id else ""
        self.default_project = SuggestCombo(names, current, "Naziv postojećeg ili novog projekta")
        self.default_project.setToolTip(
            "Redovi bez kolone Projekat idu u ovaj projekat. Ako ne postoji, biće napravljen."
        )
        self.default_project.currentTextChanged.connect(self._replan)
        form.addRow("Projekat za redove bez projekta", self.default_project)
        root.addLayout(form)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.summary)

        self.preview = QTreeWidget()
        self.preview.setColumnCount(len(COLUMNS))
        self.preview.setHeaderLabels(COLUMNS)
        self.preview.setRootIsDecorated(False)
        self.preview.setAlternatingRowColors(True)
        header = self.preview.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, w in enumerate((44, 170, 240, 160, 90, 120, 86, 86, 300)):
            self.preview.setColumnWidth(i, w)
        header.setStretchLastSection(True)
        root.addWidget(self.preview, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.import_button = QPushButton("Uvezi")
        self.import_button.setProperty("primary", True)
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.do_import)
        cancel = QPushButton("Zatvori")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.import_button)
        buttons.addWidget(cancel)
        root.addLayout(buttons)
        self._show_summary()

    # --- fajl ---
    def pick_file(self) -> None:
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        path, _ = QFileDialog.getOpenFileName(
            self, "Izaberi tabelu", docs, "Excel i CSV (*.xlsx *.xls *.csv);;Svi fajlovi (*)"
        )
        if path:
            self.load(path)

    def load(self, path: str | Path) -> bool:
        try:
            self.table = importer.read_table(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Fajl nije učitan", str(exc))
            return False
        except Exception as exc:  # oštećen ili nepodržan Excel
            QMessageBox.warning(self, "Fajl nije učitan", f"Tabela ne može da se pročita.\n\n{exc}")
            return False
        self.file_label.setText(Path(path).name)
        self.file_label.setToolTip(str(path))
        self._replan()
        return True

    def save_template(self) -> None:
        docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        path, _ = QFileDialog.getSaveFileName(
            self, "Sačuvaj šablon", str(Path(docs) / "Etapa uvoz zadataka.xlsx"), "Excel (*.xlsx)"
        )
        if not path:
            return
        target = Path(path).with_suffix(".xlsx")
        try:
            importer.write_template(target)
        except OSError as exc:
            QMessageBox.warning(self, "Šablon nije sačuvan", str(exc))
            return
        self.ctx.notify(f"Šablon je sačuvan: {target}")
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    # --- pregled ---
    def _replan(self, *_args) -> None:
        if self.table is None:
            return
        try:
            with self.ctx.session() as s:
                self.plan = importer.plan(s, self.table, self.default_project.value())
        except ValueError as exc:
            self.plan = None
            self.preview.clear()
            self.summary.setText(f"<b>Ne može da se uveze:</b> {exc}")
            self.import_button.setEnabled(False)
            return
        self._fill_preview()
        self._show_summary()

    def _fill_preview(self) -> None:
        t = theme.tokens()
        self.preview.clear()
        for r in self.plan.rows:
            v = r.values
            status = labels.TASK_STATUS.get(v.get("status"), "")
            cells = [
                str(r.line),
                r.project,
                r.title,
                r.parent,
                status,
                v.get("owner", ""),
                v["start_date"].strftime("%d.%m.%Y.") if v.get("start_date") else "",
                v["due_date"].strftime("%d.%m.%Y.") if v.get("due_date") else "",
                "; ".join(r.warnings),
            ]
            item = QTreeWidgetItem(cells)
            if r.warnings:
                item.setForeground(8, QColor(t.warning))
                item.setToolTip(8, "\n".join(r.warnings))
            if r.project in (self.plan.new_projects if self.plan else []):
                item.setToolTip(1, "Novi projekat: biće napravljen pri uvozu")
            self.preview.addTopLevelItem(item)

    def _show_summary(self) -> None:
        if self.plan is None:
            self.summary.setText(
                "Izaberi Excel (.xlsx, .xls) ili CSV fajl. Ako tabelu tek pripremaš, preuzmi "
                "šablon: u njemu su sve kolone, primer i uputstvo."
            )
            self.import_button.setEnabled(False)
            return
        p = self.plan
        parts = [f"<b>{len(p.rows)} zadataka</b> spremno za uvoz"]
        projects = sorted({r.project for r in p.rows})
        parts.append(f"projekti: {', '.join(projects)}")
        if p.new_projects:
            parts.append(f"novi projekti: <b>{', '.join(p.new_projects)}</b>")
        if p.warnings:
            parts.append(f"upozorenja: {len(p.warnings)} (kolona Napomena)")
        if p.skipped:
            parts.append(f"preskočeno: {len(p.skipped)} ({'; '.join(p.skipped[:3])})")
        lines = [" · ".join(parts)]
        recognized = ", ".join(p.mapping.values())
        lines.append(f"Prepoznate kolone: {recognized}")
        if p.unknown_columns:
            lines.append(f"Kolone koje se ne uvoze: {', '.join(p.unknown_columns)}")
        self.summary.setText("<br>".join(lines))
        self.import_button.setEnabled(bool(p.rows))
        self.import_button.setText(f"Uvezi {len(p.rows)} zadataka")

    # --- upis ---
    def do_import(self) -> None:
        if not self.plan or not self.plan.rows:
            return
        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.result = self.ctx.run(lambda s: importer.apply(s, self.plan), self)
        finally:
            QGuiApplication.restoreOverrideCursor()
        if self.result is None:
            return
        r = self.result
        text = f"Uvezeno zadataka: {r.tasks}"
        if r.projects:
            text += f", novih projekata: {r.projects}"
        if r.dependencies:
            text += f", zavisnosti: {r.dependencies}"
        self.ctx.notify(text + ".")
        self.accept()


def import_dialog(ctx: AppContext, parent: QWidget | None = None) -> importer.Result | None:
    dlg = ImportDialog(ctx, parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.result
    return None
