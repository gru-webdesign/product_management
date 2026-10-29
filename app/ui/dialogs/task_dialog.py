"""Dijalog zadatka: detalji, beleške, zavisnosti, komentari sa linka i istorija izmena."""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.db.models import DependencyType, Priority, Task, TaskStatus
from app.labels import DEPENDENCY_TYPE, FIELD, PRIORITY, TASK_STATUS
from app.services import activity
from app.services import dependencies as dep_service
from app.services import tasks as task_service
from app.ui import icons, theme
from app.ui.context import AppContext
from app.ui.widgets.fields import MoneyEdit, OptionalDateField

ROLE_ID = Qt.ItemDataRole.UserRole


def _hours_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, 9999)
    spin.setDecimals(1)
    spin.setSingleStep(0.5)
    spin.setSuffix(" h")
    spin.setSpecialValueText("—")
    return spin


class TaskDialog(QDialog):
    def __init__(
        self,
        ctx: AppContext,
        task_id: str | None = None,
        parent: QWidget | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.task_id = task_id
        self.project_id = ctx.project_id
        defaults = defaults or {}
        self.setWindowTitle("Zadatak" if task_id else "Novi zadatak")
        self.setMinimumSize(620, 560)

        with ctx.session() as s:
            task = task_service.get(s, task_id) if task_id else None
            if task:
                self.project_id = task.project_id
            excluded = ({task.id} | task_service.descendant_ids(task)) if task else set()
            self._parents = [
                (t.id, ("    " * depth) + t.title)
                for t, depth in task_service.tree(s, self.project_id)
                if t.id not in excluded
            ]
            self._all_tags = task_service.all_tags(s)
            data = self._snapshot(task) if task else None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(10)

        self.title_edit = QLineEdit(data["title"] if data else defaults.get("title", ""))
        self.title_edit.setPlaceholderText("Šta treba uraditi?")
        f = self.title_edit.font()
        f.setPointSizeF(f.pointSizeF() + 2.5)
        f.setWeight(f.Weight.DemiBold)
        self.title_edit.setFont(f)
        root.addWidget(self.title_edit)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._details_tab(data, defaults), "Detalji")
        if task_id:
            self.tabs.addTab(self._notes_tab(), "Beleške")
            self.tabs.addTab(self._deps_tab(), "Zavisnosti")
            self.tabs.addTab(self._comments_tab(), "Komentari")
            self.tabs.addTab(self._history_tab(), "Istorija")
        root.addWidget(self.tabs, 1)

        self.error = QLabel()
        self.error.setStyleSheet(f"color: {theme.tokens().danger};")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)

        bottom = QHBoxLayout()
        if task_id:
            delete = QPushButton("Obriši")
            delete.setProperty("danger", True)
            delete.setIcon(icons.icon("trash", theme.tokens().danger))
            delete.clicked.connect(self._delete)
            bottom.addWidget(delete)
            sub = QPushButton("Dodaj podzadatak")
            sub.setIcon(icons.icon("plus"))
            sub.clicked.connect(self._add_subtask)
            bottom.addWidget(sub)
        bottom.addStretch(1)
        buttons = QDialogButtonBox()
        save = buttons.addButton("Sačuvaj", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setProperty("primary", True)
        save.setDefault(True)
        buttons.addButton("Otkaži", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        root.addLayout(bottom)
        self.title_edit.setFocus()

    # --- tabovi ----------------------------------------------------------------------------------

    @staticmethod
    def _snapshot(task: Task) -> dict[str, Any]:
        return {
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "start_date": task.start_date,
            "due_date": task.due_date,
            "estimate_hours": task.estimate_hours,
            "actual_hours": task.actual_hours,
            "progress": task.progress,
            "planned_cost_minor": task.planned_cost_minor,
            "parent_id": task.parent_id,
            "tags": [t.name for t in task.tags],
        }

    def _details_tab(self, data, defaults) -> QWidget:
        d = data or {}
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(4, 14, 4, 4)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.status = QComboBox()
        for st, label in TASK_STATUS.items():
            self.status.addItem(label, st)
        self.status.setCurrentIndex(
            list(TASK_STATUS).index(d.get("status", defaults.get("status", TaskStatus.TODO)))
        )
        self.priority = QComboBox()
        for pr, label in PRIORITY.items():
            self.priority.addItem(label, pr)
        self.priority.setCurrentIndex(list(PRIORITY).index(d.get("priority", Priority.MEDIUM)))
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self.status, 1)
        row1.addSpacing(14)
        row1.addWidget(QLabel("Prioritet"))
        row1.addWidget(self.priority, 1)
        form.addRow("Status", row1)

        self.start = OptionalDateField(d.get("start_date", defaults.get("start_date")), "Postavi")
        self.due = OptionalDateField(d.get("due_date", defaults.get("due_date")), "Postavi")
        form.addRow("Početak", self.start)
        form.addRow("Rok", self.due)

        self.estimate = _hours_spin()
        self.estimate.setValue(d.get("estimate_hours") or 0)
        self.actual = _hours_spin()
        self.actual.setValue(d.get("actual_hours") or 0)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self.estimate, 1)
        row2.addSpacing(14)
        row2.addWidget(QLabel("Utrošeno"))
        row2.addWidget(self.actual, 1)
        form.addRow("Procena", row2)

        self.progress = QSpinBox()
        self.progress.setRange(0, 100)
        self.progress.setSuffix(" %")
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.setSingleStep(5)
        self.progress_slider.setPageStep(10)
        self.progress.valueChanged.connect(self.progress_slider.setValue)
        self.progress_slider.valueChanged.connect(self.progress.setValue)
        self.progress.setValue(d.get("progress", 0))
        row3 = QHBoxLayout()
        row3.addWidget(self.progress_slider, 1)
        row3.addWidget(self.progress)
        form.addRow("Progres", row3)

        self.cost = MoneyEdit(d.get("planned_cost_minor", 0))
        form.addRow("Planirani trošak", self.cost)

        self.tags = QLineEdit(", ".join(d.get("tags", [])))
        self.tags.setPlaceholderText("npr. dizajn, klijent (odvojeno zarezom)")
        completer = QCompleter(self._all_tags, self.tags)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tags.setCompleter(completer)
        form.addRow("Tagovi", self.tags)

        self.parent_combo = QComboBox()
        self.parent_combo.addItem("— nema (glavni zadatak)", None)
        for pid, label in self._parents:
            self.parent_combo.addItem(label, pid)
        wanted = d.get("parent_id", defaults.get("parent_id"))
        idx = self.parent_combo.findData(wanted) if wanted else 0
        self.parent_combo.setCurrentIndex(max(0, idx))
        form.addRow("Nadređeni", self.parent_combo)

        self.description = QPlainTextEdit(d.get("description", ""))
        self.description.setPlaceholderText("Opis, linkovi, napomene…")
        self.description.setMinimumHeight(80)
        form.addRow("Opis", self.description)
        return w

    def _notes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        row = QHBoxLayout()
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Nova beleška… (Enter)")
        self.note_edit.returnPressed.connect(self._add_note)
        add = QPushButton("Dodaj")
        add.clicked.connect(self._add_note)
        row.addWidget(self.note_edit, 1)
        row.addWidget(add)
        lay.addLayout(row)
        self.notes_list = QListWidget()
        self.notes_list.setWordWrap(True)
        self.notes_list.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        from PySide6.QtGui import QAction

        remove = QAction("Obriši belešku", self.notes_list)
        remove.triggered.connect(self._delete_note)
        self.notes_list.addAction(remove)
        lay.addWidget(self.notes_list, 1)
        self._load_notes()
        return w

    def _deps_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        hint = QLabel("Ovaj zadatak čeka na:")
        hint.setProperty("muted", True)
        lay.addWidget(hint)
        self.deps_list = QListWidget()
        lay.addWidget(self.deps_list, 1)

        row = QHBoxLayout()
        self.dep_task = QComboBox()
        with self.ctx.session() as s:
            for t, depth in task_service.tree(s, self.project_id):
                if t.id != self.task_id:
                    self.dep_task.addItem(("    " * depth) + t.title, t.id)
        self.dep_type = QComboBox()
        for dt, label in DEPENDENCY_TYPE.items():
            self.dep_type.addItem(label, dt)
        self.dep_lag = QSpinBox()
        self.dep_lag.setRange(-365, 365)
        self.dep_lag.setSuffix(" d")
        self.dep_lag.setToolTip("Kašnjenje u danima (može i negativno)")
        add = QPushButton("Dodaj")
        add.clicked.connect(self._add_dependency)
        remove = QPushButton("Ukloni izabranu")
        remove.clicked.connect(self._remove_dependency)
        row.addWidget(self.dep_task, 2)
        row.addWidget(self.dep_type, 1)
        row.addWidget(self.dep_lag)
        row.addWidget(add)
        lay.addLayout(row)
        lay.addWidget(remove, 0, Qt.AlignmentFlag.AlignLeft)
        info = QLabel(
            "Kad se prethodni zadatak pomeri kasnije, ovaj se automatski pomera za isto "
            "da bi zavisnost ostala ispunjena."
        )
        info.setWordWrap(True)
        info.setProperty("faint", True)
        lay.addWidget(info)
        self._load_deps()
        return w

    def _comments_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        from app.ui.widgets.comments_panel import CommentsPanel

        self.comments = CommentsPanel(self.ctx, task_id=self.task_id)
        lay.addWidget(self.comments)
        return w

    def _history_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        lst = QListWidget()
        lst.setWordWrap(True)
        with self.ctx.session() as s:
            for h in activity.history(s, self.task_id):
                when = h.created_at.astimezone().strftime("%d.%m.%Y. %H:%M")
                if h.action == "create":
                    text = "Zadatak napravljen"
                elif h.field == "dependency":
                    text = (
                        f"Dodata zavisnost: čeka na „{h.new_value}“"
                        if h.new_value != "—"
                        else f"Uklonjena zavisnost od „{h.old_value}“"
                    )
                else:
                    label = FIELD.get(h.field, h.field)
                    text = f"{label.capitalize()}: {h.old_value} → {h.new_value}"
                lst.addItem(f"{when}   {text}")
        if lst.count() == 0:
            lst.addItem("Još nema izmena.")
        lay.addWidget(lst)
        return w

    # --- akcije ----------------------------------------------------------------------------------

    def values(self) -> dict[str, Any]:
        return {
            "title": self.title_edit.text().strip(),
            "status": self.status.currentData(),
            "priority": self.priority.currentData(),
            "start_date": self.start.value(),
            "due_date": self.due.value(),
            "estimate_hours": self.estimate.value() or None,
            "actual_hours": self.actual.value() or None,
            "progress": self.progress.value(),
            "planned_cost_minor": self.cost.value_minor() if self.cost.is_valid() else -1,
            "parent_id": self.parent_combo.currentData(),
            "description": self.description.toPlainText().strip(),
            "tags": [t for t in self.tags.text().split(",") if t.strip()],
        }

    def _save(self) -> None:
        values = self.values()
        if not values["title"]:
            return self._fail("Unesi naziv zadatka.")
        if values["planned_cost_minor"] < 0:
            return self._fail("Planirani trošak nije ispravan iznos.")
        start, due = values["start_date"], values["due_date"]
        if start and due and start > due:
            return self._fail("Početak mora biti pre roka.")

        def work(s):
            if self.task_id:
                task = task_service.get(s, self.task_id)
                changes = dict(values)
                # Prebacivanje u „Završeno“ podiže progres na 100%, osim ako ga je korisnik
                # u istom koraku sam promenio.
                just_done = changes["status"] == TaskStatus.DONE != task.status
                if just_done and changes["progress"] == task.progress:
                    changes["progress"] = 100
                task_service.update(s, task, **changes)
                return task.id
            tags = values.pop("tags")
            if values["status"] == TaskStatus.DONE:
                values["progress"] = 100
            return task_service.create(s, self.project_id, tags=tags, **values).id

        result = self.ctx.run(work, self)
        if result:
            self.task_id = result
            self.accept()

    def _fail(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()

    def _delete(self) -> None:
        with self.ctx.session() as s:
            task = task_service.get(s, self.task_id)
            n = len(task_service.descendant_ids(task))
            title = task.title
        extra = f" i njegovih {n} podzadataka" if n else ""
        answer = QMessageBox.question(self, "Obriši zadatak", f"Obrisati „{title}“{extra}?")
        if answer == QMessageBox.StandardButton.Yes:
            self.ctx.run(lambda s: task_service.delete(s, task_service.get(s, self.task_id)))
            self.ctx.notify(f"Zadatak „{title}“ je obrisan.")
            self.done(2)

    def _add_subtask(self) -> None:
        parent_id = self.task_id
        self.done(3)
        open_new_task(self.ctx, self.parentWidget(), parent_id=parent_id)

    def _load_notes(self) -> None:
        self.notes_list.clear()
        with self.ctx.session() as s:
            for n in task_service.notes(s, self.task_id):
                item = QListWidgetItem(
                    f"{n.created_at.astimezone().strftime('%d.%m.%Y. %H:%M')}\n{n.text}"
                )
                item.setData(ROLE_ID, n.id)
                self.notes_list.addItem(item)

    def _add_note(self) -> None:
        text = self.note_edit.text()
        if not text.strip():
            return
        if self.ctx.run(
            lambda s: task_service.add_note(s, task_service.get(s, self.task_id), text), self
        ):
            self.note_edit.clear()
            self._load_notes()

    def _delete_note(self) -> None:
        item = self.notes_list.currentItem()
        if not item:
            return
        from app.db.models import Note

        note_id = item.data(ROLE_ID)
        self.ctx.run(lambda s: task_service.delete_note(s, s.get(Note, note_id)), self)
        self._load_notes()

    def _load_deps(self) -> None:
        self.deps_list.clear()
        with self.ctx.session() as s:
            task = task_service.get(s, self.task_id)
            for dep in task.predecessors:
                label = DEPENDENCY_TYPE[dep.type]
                lag = f", kašnjenje {dep.lag_days} d" if dep.lag_days else ""
                item = QListWidgetItem(f"{dep.predecessor.title}   ({label}{lag})")
                item.setData(ROLE_ID, dep.id)
                self.deps_list.addItem(item)
        if self.deps_list.count() == 0:
            item = QListWidgetItem("Nema zavisnosti.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.deps_list.addItem(item)

    def _add_dependency(self) -> None:
        pred_id = self.dep_task.currentData()
        if not pred_id:
            return
        dep_type: DependencyType = self.dep_type.currentData()
        lag = self.dep_lag.value()

        def work(s):
            dep_service.add(
                s, task_service.get(s, pred_id), task_service.get(s, self.task_id), dep_type, lag
            )
            return True

        if self.ctx.run(work, self):
            self._load_deps()
            self._refresh_dates()

    def _remove_dependency(self) -> None:
        item = self.deps_list.currentItem()
        dep_id = item.data(ROLE_ID) if item else None
        if not dep_id:
            return
        from app.db.models import TaskDependency

        self.ctx.run(lambda s: dep_service.remove(s, s.get(TaskDependency, dep_id)), self)
        self._load_deps()

    def _refresh_dates(self) -> None:
        """Dodavanje zavisnosti može pomeriti datume — prikaži nove u formi."""
        with self.ctx.session() as s:
            task = task_service.get(s, self.task_id)
            start, due = task.start_date, task.due_date
        self.start.set_value(start)
        self.due.set_value(due)


def open_new_task(ctx: AppContext, parent: QWidget | None = None, **defaults) -> str | None:
    dlg = TaskDialog(ctx, None, parent, defaults=defaults)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        ctx.notify("Zadatak je dodat.")
        return dlg.task_id
    return None


def open_task(ctx: AppContext, task_id: str, parent: QWidget | None = None) -> None:
    TaskDialog(ctx, task_id, parent).exec()


def default_dates_for_new() -> tuple[date, date]:
    today = date.today()
    return today, today
