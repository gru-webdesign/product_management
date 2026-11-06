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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.db.models import DependencyType, Priority, Task, TaskStatus
from app.labels import DEPENDENCY_TYPE, FIELD, PRIORITY, TASK_STATUS, steps_for
from app.services import activity, suggestions
from app.services import dependencies as dep_service
from app.services import tasks as task_service
from app.ui import icons, theme
from app.ui.context import AppContext
from app.ui.widgets.fields import MoneyEdit, OptionalDateField, SuggestCombo

ROLE_ID = Qt.ItemDataRole.UserRole


def _hours_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, 9999)
    spin.setDecimals(1)
    spin.setSingleStep(0.5)
    spin.setSuffix(" h")
    spin.setSpecialValueText("-")
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
            # kandidati za „Deo zadatka“: (id, naziv, dubina, faza)
            candidates = [
                (t, depth)
                for t, depth in task_service.tree(s, self.project_id)
                if t.id not in excluded
            ]
            self._parents = [(t.id, t.title, depth, t.phase or "") for t, depth in candidates]
            self._work_types = {t.id: t.work_type or "" for t, _ in candidates}
            # postojeći koraci (podzadaci): id, naziv, završen, nosilac
            self._steps = (
                [
                    {
                        "id": c.id,
                        "title": c.title,
                        "done": c.status == TaskStatus.DONE,
                        "owner": c.owner,
                        "was_done": c.status == TaskStatus.DONE,
                    }
                    for c in sorted(task.subtasks, key=lambda c: c.sort_order)
                ]
                if task
                else []
            )
            self._all_tags = task_service.all_tags(s)
            self._suggest = {
                f: suggestions.for_field(s, f) for f in ("work_type", "phase", "people")
            }
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
        self.tabs.addTab(self._steps_tab(), "Koraci")
        self._render_steps()
        # zavisnosti novog zadatka se pamte i upisuju pri čuvanju
        self._pending_deps: list[tuple[str, DependencyType, int, str]] = []
        self.tabs.addTab(self._deps_tab(), "Zavisnosti")
        if task_id:
            self.tabs.addTab(self._notes_tab(), "Beleške")
            self.tabs.addTab(self._time_tab(), "Vreme")
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
            "has_time": bool(task.time_entries),
            "work_type": task.work_type,
            "phase": task.phase,
            "owner": task.owner,
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

        self.owner = SuggestCombo(
            self._suggest["people"], d.get("owner", defaults.get("owner", "")), "osoba ili tim"
        )
        form.addRow("Nosilac", self.owner)
        self.work_type = SuggestCombo(self._suggest["work_type"], d.get("work_type", ""))
        self.phase = SuggestCombo(self._suggest["phase"], d.get("phase", defaults.get("phase", "")))
        row_kind = QHBoxLayout()
        row_kind.setSpacing(8)
        row_kind.addWidget(self.work_type, 1)
        row_kind.addSpacing(14)
        row_kind.addWidget(QLabel("Faza"))
        row_kind.addWidget(self.phase, 1)
        form.addRow("Vrsta rada", row_kind)

        self.start = OptionalDateField(d.get("start_date", defaults.get("start_date")), "Postavi")
        self.due = OptionalDateField(d.get("due_date", defaults.get("due_date")), "Postavi")
        form.addRow("Početak", self.start)
        form.addRow("Rok", self.due)

        self.estimate = _hours_spin()
        self.estimate.setValue(d.get("estimate_hours") or 0)
        self.actual = _hours_spin()
        self.actual.setValue(d.get("actual_hours") or 0)
        self._has_time = bool(d.get("has_time"))
        if self._has_time:
            self.actual.setEnabled(False)
            self.actual.setToolTip("Zbir unosa iz taba Vreme")
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
        self.tags.setPlaceholderText("npr. TNapp, partner, regulativa (odvojeno zarezom)")
        completer = QCompleter(self._all_tags, self.tags)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tags.setCompleter(completer)
        form.addRow("Tagovi", self.tags)

        self.parent_combo = QComboBox()
        self.parent_combo.setMaxVisibleItems(18)
        self.parent_combo.setToolTip(
            "Ako je ovaj zadatak korak većeg zadatka, izaberi taj zadatak. "
            "Prvo su ponuđeni zadaci iz iste faze, pa iste vrste rada, pa ostali."
        )
        self._fill_parents(d.get("parent_id", defaults.get("parent_id")))
        self.phase.currentTextChanged.connect(self._phase_changed)
        form.addRow("Deo zadatka", self.parent_combo)

        self.description = QPlainTextEdit(d.get("description", ""))
        self.description.setPlaceholderText("Opis, kriterijumi prihvatanja, linkovi, napomene…")
        self.description.setMinimumHeight(80)
        form.addRow("Opis", self.description)
        return w

    def _fill_parents(self, wanted: str | None) -> None:
        """Zadaci razvrstani po temi: prvo ista faza, pa ista vrsta rada, pa svi ostali.

        Pored zadataka iz drugih grupa piše njihova faza, da se odmah vidi gde pripadaju.
        """
        phase = self.phase.value()
        work = self.work_type.value() if hasattr(self, "work_type") else ""
        combo = self.parent_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("Samostalan zadatak (nije deo drugog)", None)
            if not self._parents:
                combo.addItem("U projektu još nema drugih zadataka", "__header__")
                combo.model().item(1).setEnabled(False)
                return
            by_task = {pid: work_type for pid, work_type in self._work_types.items()}
            same_phase = [x for x in self._parents if phase and x[3].casefold() == phase.casefold()]
            same_work = [
                x
                for x in self._parents
                if x not in same_phase
                and work
                and by_task.get(x[0], "").casefold() == work.casefold()
            ]
            rest = [x for x in self._parents if x not in same_phase and x not in same_work]
            groups = [
                (same_phase, f"Faza: {phase}", False),
                (same_work, f"Vrsta rada: {work}", True),
                (rest, "Ostali zadaci" if same_phase or same_work else "", True),
            ]
            for group, header, show_phase in groups:
                if not group:
                    continue
                if header:
                    combo.insertSeparator(combo.count())
                    combo.addItem(header, "__header__")
                    combo.model().item(combo.count() - 1).setEnabled(False)
                for pid, title, depth, ph in group:
                    label = ("    " * depth) + title
                    if ph and show_phase:
                        label += f"   ·  {ph}"
                    combo.addItem(label, pid)
        finally:
            idx = combo.findData(wanted) if wanted else 0
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

    def _phase_changed(self, _text: str) -> None:
        self._fill_parents(self.parent_combo.currentData())

    # --- koraci (podzadaci) ---
    def _steps_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        hint = QLabel(
            "Koraci su podzadaci ovog zadatka, od početka do kraja. Štikliraj završene; "
            "napredak zadatka se vidi u Listi, Kanbanu i Gantu."
        )
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        lay.addWidget(hint)
        self.steps_list = QListWidget()
        self.steps_list.setObjectName("Steps")
        self.steps_list.itemChanged.connect(self._step_toggled)
        lay.addWidget(self.steps_list, 1)

        row = QHBoxLayout()
        self.step_input = SuggestCombo([], "", "Novi korak: izaberi predlog ili upiši")
        self.step_input.lineEdit().returnPressed.connect(self._add_step)
        add = QPushButton("Dodaj")
        add.clicked.connect(self._add_step)
        row.addWidget(self.step_input, 1)
        row.addWidget(add)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        self.suggest_steps = QPushButton()
        self.suggest_steps.setIcon(icons.icon("plus"))
        self.suggest_steps.clicked.connect(self._add_suggested_steps)
        self.remove_step = QPushButton("Ukloni novi korak")
        self.remove_step.setToolTip("Uklanja korak koji još nije sačuvan")
        self.remove_step.clicked.connect(self._remove_step)
        row2.addWidget(self.suggest_steps)
        row2.addStretch(1)
        row2.addWidget(self.remove_step)
        lay.addLayout(row2)
        self.work_type.currentTextChanged.connect(self._refresh_step_suggestions)
        self.work_type.currentTextChanged.connect(self._phase_changed)
        self._render_steps()
        self._refresh_step_suggestions()
        return w

    def _render_steps(self) -> None:
        self.steps_list.blockSignals(True)
        self.steps_list.clear()
        for i, step in enumerate(self._steps):
            text = step["title"] + (f"   ·  {step['owner']}" if step.get("owner") else "")
            if not step["id"]:
                text += "   (novo)"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if step["done"] else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.steps_list.addItem(item)
        self.steps_list.blockSignals(False)
        i = self.tabs.indexOf(self.steps_list.parentWidget()) if hasattr(self, "tabs") else -1
        if i >= 0:
            done = sum(s["done"] for s in self._steps)
            self.tabs.setTabText(
                i, f"Koraci {done}/{len(self._steps)}" if self._steps else "Koraci"
            )

    def _step_suggestions(self) -> list[str]:
        have = {s["title"].casefold() for s in self._steps}
        return [x for x in steps_for(self.work_type.value()) if x.casefold() not in have]

    def _refresh_step_suggestions(self, *_args) -> None:
        free = self._step_suggestions()
        text = self.step_input.currentText()
        self.step_input.clear()
        self.step_input.addItems(free)
        self.step_input.setCurrentIndex(-1)
        self.step_input.setCurrentText(text)
        kind = self.work_type.value() or "opšti"
        self.suggest_steps.setText(f"Dodaj predložene korake za: {kind} ({len(free)})")
        self.suggest_steps.setEnabled(bool(free))

    def _append_step(self, title: str) -> bool:
        title = " ".join(title.split())
        if not title or title.casefold() in {s["title"].casefold() for s in self._steps}:
            return False
        self._steps.append(
            {"id": None, "title": title, "done": False, "owner": "", "was_done": False}
        )
        return True

    def _add_step(self) -> None:
        if self._append_step(self.step_input.currentText()):
            self.step_input.setCurrentText("")
            self._render_steps()
            self._refresh_step_suggestions()

    def _add_suggested_steps(self) -> None:
        for title in self._step_suggestions():
            self._append_step(title)
        self._render_steps()
        self._refresh_step_suggestions()

    def _remove_step(self) -> None:
        item = self.steps_list.currentItem()
        if item is None:
            return
        step = self._steps[item.data(Qt.ItemDataRole.UserRole)]
        if step["id"]:
            self._fail("Sačuvan korak se briše iz Liste (desni klik na podzadatak).")
            return
        self._steps.remove(step)
        self._render_steps()
        self._refresh_step_suggestions()

    def _step_toggled(self, item: QListWidgetItem) -> None:
        step = self._steps[item.data(Qt.ItemDataRole.UserRole)]
        step["done"] = item.checkState() == Qt.CheckState.Checked
        self._render_steps()

    def _save_steps(self, s, task) -> None:
        """Novi koraci se prave, a štiklirani/odštiklirani menjaju status."""
        new = [st["title"] for st in self._steps if not st["id"]]
        created = {c.title: c for c in task_service.add_steps(s, task, new)}
        for st in self._steps:
            target = task_service.get(s, st["id"]) if st["id"] else created.get(st["title"])
            if target is None:
                continue
            if st["done"] and target.status != TaskStatus.DONE:
                task_service.update(s, target, status=TaskStatus.DONE, progress=100)
            elif not st["done"] and st["was_done"]:
                task_service.update(s, target, status=TaskStatus.TODO)

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

    def _time_tab(self) -> QWidget:
        from app.services import timetracking as tt
        from app.ui.widgets.fields import date_edit

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 12, 4, 4)
        top = QHBoxLayout()
        self.timer_button = QPushButton()
        self.timer_button.clicked.connect(self._toggle_timer)
        top.addWidget(self.timer_button)
        top.addStretch(1)
        self.time_total = QLabel()
        self.time_total.setProperty("muted", True)
        top.addWidget(self.time_total)
        lay.addLayout(top)

        self.time_list = QTreeWidget()
        self.time_list.setHeaderLabels(["Datum", "Sati", "Opis"])
        self.time_list.setRootIsDecorated(False)
        self.time_list.setUniformRowHeights(True)
        head = self.time_list.header()
        head.setStretchLastSection(True)
        head.setSectionResizeMode(0, head.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, head.ResizeMode.ResizeToContents)
        self.time_list.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        from PySide6.QtGui import QAction

        remove = QAction("Obriši unos", self.time_list)
        remove.triggered.connect(self._delete_time)
        self.time_list.addAction(remove)
        lay.addWidget(self.time_list, 1)

        add_row = QHBoxLayout()
        self.time_date = date_edit()
        self.time_hours = QDoubleSpinBox()
        self.time_hours.setRange(0, 24)
        self.time_hours.setDecimals(2)
        self.time_hours.setSingleStep(0.25)
        self.time_hours.setSuffix(" h")
        self.time_note = QLineEdit()
        self.time_note.setPlaceholderText("Šta je rađeno (opciono)")
        add = QPushButton("Dodaj")
        add.clicked.connect(self._add_time)
        add_row.addWidget(self.time_date)
        add_row.addWidget(self.time_hours)
        add_row.addWidget(self.time_note, 1)
        add_row.addWidget(add)
        lay.addLayout(add_row)
        hint = QLabel(
            "Sati se sabiraju u „Utrošeno“, a u budžetu se vrednuju po satnici iz podešavanja."
        )
        hint.setWordWrap(True)
        hint.setProperty("faint", True)
        lay.addWidget(hint)
        self._tt = tt
        self._load_time()
        return w

    def _load_time(self) -> None:
        tt = self._tt
        self.time_list.clear()
        with self.ctx.session() as s:
            rows = [(e.id, e.date, e.hours, e.note) for e in tt.entries(s, self.task_id)]
            total = tt.total_hours(s, self.task_id)
            running = tt.running(s)
        mono = theme.mono(self.time_list.font())
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for eid, day, hours, note in rows:
            item = QTreeWidgetItem([day.strftime("%d.%m.%Y."), tt.format_hours(hours), note])
            item.setData(0, ROLE_ID, eid)
            item.setFont(0, mono)
            item.setFont(1, mono)
            item.setTextAlignment(1, right)
            self.time_list.addTopLevelItem(item)
        if not rows:
            empty = QTreeWidgetItem(["", "", "Još nema upisanog vremena."])
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.time_list.addTopLevelItem(empty)
        self.time_total.setText(f"Ukupno: {tt.format_hours(total)}" if total else "")
        on_this = running is not None and running.task_id == self.task_id
        self.timer_button.setText("Zaustavi tajmer" if on_this else "Pokreni tajmer")
        self.timer_button.setIcon(icons.icon("stop" if on_this else "play"))
        if self._has_time or rows:
            self._has_time = True
            self.actual.setEnabled(False)
            self.actual.setValue(total)

    def _toggle_timer(self) -> None:
        from app.ui.widgets.timer_widget import start_timer, stop_timer

        with self.ctx.session() as s:
            running = self._tt.running(s)
        if running is not None and running.task_id == self.task_id:
            stop_timer(self.ctx, self)
        else:
            start_timer(self.ctx, self.task_id, self)
        self._load_time()

    def _add_time(self) -> None:
        from app.ui.widgets.fields import from_qdate

        day, hours = from_qdate(self.time_date.date()), self.time_hours.value()
        note = self.time_note.text()
        if self.ctx.run(lambda s: self._tt.add_entry(s, self.task_id, day, hours, note), self):
            self.time_hours.setValue(0)
            self.time_note.clear()
            self._load_time()

    def _delete_time(self) -> None:
        item = self.time_list.currentItem()
        eid = item.data(0, ROLE_ID) if item else None
        if not eid:
            return
        from app.db.models import TimeEntry

        self.ctx.run(lambda s: self._tt.delete_entry(s, s.get(TimeEntry, eid)), self)
        self._load_time()

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
                        if h.new_value != "prazno"
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
            **({} if self._has_time else {"actual_hours": self.actual.value() or None}),
            "progress": self.progress.value(),
            "planned_cost_minor": self.cost.value_minor() if self.cost.is_valid() else -1,
            "parent_id": (
                None
                if self.parent_combo.currentData() == "__header__"
                else self.parent_combo.currentData()
            ),
            "description": self.description.toPlainText().strip(),
            "tags": [t for t in self.tags.text().split(",") if t.strip()],
            "work_type": self.work_type.value(),
            "phase": self.phase.value(),
            "owner": self.owner.value(),
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
                self._save_steps(s, task)
                return task.id
            tags = values.pop("tags")
            if values["status"] == TaskStatus.DONE:
                values["progress"] = 100
            task = task_service.create(s, self.project_id, tags=tags, **values)
            self._save_steps(s, task)
            for pred_id, dep_type, lag, _title in self._pending_deps:
                dep_service.add(s, task_service.get(s, pred_id), task, dep_type, lag)
            return task.id

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
        for i, (_pid, dep_type, lag, title) in enumerate(self._pending_deps):
            extra = f", kašnjenje {lag} d" if lag else ""
            item = QListWidgetItem(f"{title}   ({DEPENDENCY_TYPE[dep_type]}{extra})")
            item.setData(ROLE_ID, f"pending:{i}")
            self.deps_list.addItem(item)
        if not self.task_id:
            if self.deps_list.count() == 0:
                item = QListWidgetItem("Nema zavisnosti. Zadatak može da počne odmah.")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.deps_list.addItem(item)
            return
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
        if not self.task_id:
            if all(d[0] != pred_id for d in self._pending_deps):
                title = self.dep_task.currentText().strip()
                self._pending_deps.append((pred_id, dep_type, lag, title))
            self._load_deps()
            return

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
        if dep_id.startswith("pending:"):
            del self._pending_deps[int(dep_id.split(":")[1])]
            self._load_deps()
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
