"""Tab „Registar“: rizici i problemi, zainteresovane strane, dokumenta i linkovi, odluke."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app import labels
from app.db.models import DecisionStatus, DocStatus, RiskKind, RiskStatus
from app.services import registry, suggestions
from app.services import tasks as task_service
from app.ui import icons, theme
from app.ui.dialogs.registry_dialogs import (
    DecisionDialog,
    DocumentDialog,
    RiskDialog,
    StakeholderDialog,
)
from app.ui.views.base import ProjectView
from app.ui.widgets.card import Card
from app.ui.widgets.paint import PillDelegate

ROLE_ID = Qt.ItemDataRole.UserRole


def _fmt(d: date | None) -> str:
    return d.strftime("%d.%m.%Y.") if d else ""


def risk_colors(t) -> dict:
    return {
        "level": {"Kritičan": t.danger, "Visok": t.warning, "Srednji": t.accent, "Nizak": t.faint},
        "kind": {
            RiskKind.RISK: t.warning,
            RiskKind.ISSUE: t.danger,
            RiskKind.ASSUMPTION: t.faint,
            RiskKind.DEPENDENCY: t.accent,
        },
        "status": {
            RiskStatus.OPEN: t.warning,
            RiskStatus.IN_PROGRESS: t.accent,
            RiskStatus.ACCEPTED: t.faint,
            RiskStatus.CLOSED: t.success,
        },
    }


def doc_colors(t) -> dict:
    return {
        DocStatus.DRAFT: t.faint,
        DocStatus.REVIEW: t.warning,
        DocStatus.APPROVED: t.success,
        DocStatus.OBSOLETE: t.border_strong,
    }


def decision_colors(t) -> dict:
    return {
        DecisionStatus.PROPOSED: t.warning,
        DecisionStatus.APPROVED: t.success,
        DecisionStatus.REJECTED: t.danger,
        DecisionStatus.SUPERSEDED: t.faint,
    }


def raci_colors(t) -> dict:
    return {"A": t.accent, "R": t.success, "C": t.warning, "I": t.faint}


class Section:
    """Jedan deo registra: kolone, dijalog, punjenje redova i tekst za prazno stanje."""

    def __init__(self, key, label, add_label, icon, columns, widths, pills, dialog, empty):
        self.key, self.label, self.add_label, self.icon = key, label, add_label, icon
        self.columns, self.widths, self.pills = columns, widths, pills
        self.dialog, self.empty = dialog, empty
        self.kind = registry.KINDS[key]


SECTIONS = [
    Section(
        "risk",
        "Rizici i problemi",
        "Rizik",
        "risk",
        ["Naziv", "Vrsta", "Ocena", "Status", "Nosilac", "Rok", "Mera"],
        {1: 130, 2: 120, 3: 110, 4: 150, 5: 100, 6: 260},
        (1, 2, 3),
        RiskDialog,
        "Još nema rizika ni problema. Dodaj prvi dugmetom „Rizik“: šta može da pođe "
        "naopako, koliko je verovatno i kakav je uticaj.",
    ),
    Section(
        "stakeholder",
        "Zainteresovane strane",
        "Osoba",
        "users",
        ["Ime / tim", "Organizacija", "Uloga", "RACI", "Uticaj", "Interes", "Kontakt"],
        {1: 150, 2: 180, 3: 170, 4: 90, 5: 90, 6: 230},
        (3,),
        StakeholderDialog,
        "Još nema zainteresovanih strana. Dodaj ljude i timove koji odlučuju, rade ili treba "
        "da budu informisani (RACI).",
    ),
    Section(
        "document",
        "Dokumenta i linkovi",
        "Dokument",
        "document",
        ["Naziv", "Vrsta", "Verzija", "Status", "Nosilac", "Datum", "Lokacija"],
        {1: 200, 2: 70, 3: 110, 4: 140, 5: 100, 6: 260},
        (3,),
        DocumentDialog,
        "Još nema dokumenata. Dodaj specifikacije, ugovore, zapisnike ili linkove ka "
        "SharePoint-u i Confluence-u; dupli klik na lokaciju ih otvara.",
    ),
    Section(
        "decision",
        "Odluke",
        "Odluka",
        "decision",
        ["Datum", "Odluka", "Status", "Odobrio", "Obrazloženje", "Zadatak"],
        {0: 100, 2: 110, 3: 170, 4: 300, 5: 180},
        (2,),
        DecisionDialog,
        "Još nema odluka. Beleži šta je odlučeno, zašto i ko je odobrio, da se kasnije zna "
        "kako se do rešenja došlo.",
    ),
]


class RegistryView(ProjectView):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 0, 8, 4)
        bar.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.section_buttons: list[QToolButton] = []
        for i, sec in enumerate(SECTIONS):
            b = QToolButton()
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setText(sec.label)
            self.group.addButton(b, i)
            self.section_buttons.append(b)
            bar.addWidget(b)
        self.group.idClicked.connect(self._switch)
        bar.addStretch(1)
        self.show_closed = QCheckBox("Prikaži zatvorene")
        self.show_closed.toggled.connect(lambda _c: self.refresh())
        bar.addWidget(self.show_closed)
        self.add_button = QPushButton()
        self.add_button.setProperty("primary", True)
        self.add_button.clicked.connect(lambda: self.add())
        bar.addWidget(self.add_button)
        lay.addLayout(bar)

        self.stack = QStackedWidget()
        self.trees: list[QTreeWidget] = []
        self.empties: list[QLabel] = []
        for i, sec in enumerate(SECTIONS):
            card = Card(padding=(8, 4, 8, 8))
            tree = QTreeWidget()
            tree.setHeaderLabels(sec.columns)
            tree.setRootIsDecorated(False)
            tree.setUniformRowHeights(True)
            tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda pos, i=i: self._menu(i, pos))
            tree.itemDoubleClicked.connect(
                lambda item, col, i=i: QTimer.singleShot(0, lambda: self._activated(i, item, col))
            )
            for col in sec.pills:
                tree.setItemDelegateForColumn(col, PillDelegate(tree))
            header = tree.header()
            header.setStretchLastSection(False)
            stretch = 0 if sec.key != "decision" else 1
            header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
            for col, width in sec.widths.items():
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
                tree.setColumnWidth(col, width)
            empty = QLabel(sec.empty)
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setProperty("muted", True)
            empty.setContentsMargins(40, 30, 40, 30)
            card.body.addWidget(tree, 1)
            card.body.addWidget(empty, 1)
            self.trees.append(tree)
            self.empties.append(empty)
            self.stack.addWidget(card)
        lay.addWidget(self.stack, 1)

        self.section_buttons[0].setChecked(True)
        self._index = 0
        theme.manager().changed.connect(self._theme_changed)
        self._theme_changed()

    # --- izgled ----------------------------------------------------------------------------------

    def _theme_changed(self) -> None:
        t = theme.tokens()
        for b, sec in zip(self.section_buttons, SECTIONS, strict=True):
            b.setIcon(icons.icon(sec.icon))
        self.add_button.setIcon(icons.icon("plus", t.primary_text))
        self.setStyleSheet(
            f"QToolButton#Segment {{ padding: 7px 12px; border-radius: 8px; color: {t.muted};"
            " font-weight: 500; border: 1px solid transparent; }"
            f"QToolButton#Segment:hover {{ color: {t.text}; background: {t.surface_alt}; }}"
            f"QToolButton#Segment:checked {{ color: {t.text}; background: {t.surface};"
            f" border: 1px solid {t.border}; font-weight: 600; }}"
        )
        if self.isVisible():
            self.refresh()

    def _switch(self, index: int) -> None:
        self._index = index
        self.stack.setCurrentIndex(index)
        self._update_bar()

    def _update_bar(self) -> None:
        sec = SECTIONS[self._index]
        self.add_button.setText(sec.add_label)
        self.show_closed.setVisible(sec.key == "risk")

    def select_section(self, key: str) -> None:
        index = next(i for i, s in enumerate(SECTIONS) if s.key == key)
        self.section_buttons[index].setChecked(True)
        self._switch(index)

    # --- punjenje --------------------------------------------------------------------------------

    def reload(self) -> None:
        pid = self.ctx.project_id
        t = theme.tokens()
        with self.ctx.session() as s:
            risks = registry.risks(s, pid, include_closed=self.show_closed.isChecked())
            all_risks = registry.risks(s, pid)
            rows = {
                "risk": [self._risk_row(r, t) for r in risks],
                "stakeholder": [self._stakeholder_row(x, t) for x in registry.stakeholders(s, pid)],
                "document": [self._document_row(d, t) for d in registry.documents(s, pid)],
                "decision": [self._decision_row(d, t) for d in registry.decisions(s, pid)],
            }
            counts = {
                "risk": sum(1 for r in all_risks if r.status in registry.OPEN_RISK),
                "stakeholder": len(rows["stakeholder"]),
                "document": len(rows["document"]),
                "decision": len(rows["decision"]),
            }
        for i, sec in enumerate(SECTIONS):
            n = counts[sec.key]
            self.section_buttons[i].setText(f"{sec.label}  {n}" if n else sec.label)
            self._fill(i, rows[sec.key])
        self._update_bar()

    def _fill(self, index: int, rows: list[tuple[str, list, dict]]) -> None:
        tree, empty = self.trees[index], self.empties[index]
        selected = {it.data(0, ROLE_ID) for it in tree.selectedItems()}
        tree.clear()
        for item_id, texts, extra in rows:
            item = QTreeWidgetItem([str(x) for x in texts])
            item.setData(0, ROLE_ID, item_id)
            for col, color in extra.get("pills", {}).items():
                item.setData(col, PillDelegate.COLOR_ROLE, color)
            for col, color in extra.get("fg", {}).items():
                item.setForeground(col, QColor(color))
            for col, tip in extra.get("tips", {}).items():
                item.setToolTip(col, tip)
            tree.addTopLevelItem(item)
            item.setSelected(item_id in selected)
        has = bool(rows)
        tree.setVisible(has)
        if index == 0 and not has and not self.show_closed.isChecked():
            empty.setText(SECTIONS[0].empty)
        empty.setVisible(not has)

    def _risk_row(self, r, t):
        colors = risk_colors(t)
        level = labels.risk_level(r.score)
        closed = r.status not in registry.OPEN_RISK
        texts = [
            r.title,
            labels.RISK_KIND[r.kind],
            f"{level} {r.score}",
            labels.RISK_STATUS[r.status],
            r.owner,
            _fmt(r.due_date),
            r.mitigation.splitlines()[0] if r.mitigation else "",
        ]
        overdue = r.due_date and r.due_date < date.today() and not closed
        extra = {
            "pills": {
                1: colors["kind"][r.kind],
                2: colors["level"][level] if not closed else t.faint,
                3: colors["status"][r.status],
            },
            "fg": {0: t.faint} if closed else ({5: t.danger} if overdue else {}),
            "tips": {
                0: f"{r.title}\n\n{r.description}".strip(),
                2: f"Verovatnoća: {labels.PROBABILITY[r.probability]}, "
                f"uticaj: {labels.IMPACT[r.impact]}",
                6: r.mitigation,
            },
        }
        return r.id, texts, extra

    def _stakeholder_row(self, x, t):
        contact = ", ".join(v for v in (x.email, x.phone) if v)
        texts = [
            x.name,
            x.organization,
            x.role,
            x.raci,
            labels.LEVEL3[x.influence],
            labels.LEVEL3[x.interest],
            contact,
        ]
        extra = {
            "pills": {3: raci_colors(t)[x.raci]},
            "tips": {0: x.notes or x.name, 3: labels.RACI[x.raci]},
        }
        return x.id, texts, extra

    def _document_row(self, d, t):
        texts = [
            d.title,
            d.kind,
            d.version,
            labels.DOC_STATUS[d.status],
            d.owner,
            _fmt(d.doc_date),
            d.location,
        ]
        extra = {
            "pills": {3: doc_colors(t)[d.status]},
            "fg": {6: t.accent} if d.location else {},
            "tips": {0: d.notes or d.title, 6: "Dupli klik otvara" if d.location else ""},
        }
        if d.status == DocStatus.OBSOLETE:
            extra["fg"][0] = t.faint
        return d.id, texts, extra

    def _decision_row(self, d, t):
        texts = [
            _fmt(d.decided_on),
            d.title,
            labels.DECISION_STATUS[d.status],
            d.approved_by,
            d.rationale.splitlines()[0] if d.rationale else "",
            d.task.title if d.task else "",
        ]
        extra = {
            "pills": {2: decision_colors(t)[d.status]},
            "tips": {1: f"{d.title}\n\n{d.decision}".strip(), 4: d.rationale},
        }
        return d.id, texts, extra

    # --- akcije ----------------------------------------------------------------------------------

    def _context(self):
        pid = self.ctx.project_id
        with self.ctx.session() as s:
            tasks = [
                (task.id, ("    " * depth) + task.title)
                for task, depth in task_service.tree(s, pid)
            ]
            suggest = {
                f: suggestions.for_field(s, f) for f in ("people", "doc_kind", "organization")
            }
        return tasks, suggest

    def add(self, key: str | None = None):
        if key:
            self.select_section(key)
        sec = SECTIONS[self._index]
        tasks, suggest = self._context()
        dlg = sec.dialog(None, tasks, suggest, self.window())
        if not dlg.exec():
            return None
        values, pid = dlg.values(), self.ctx.project_id
        created = self.ctx.run(lambda s: registry.create(s, sec.kind, pid, **values).id, self)
        if created:
            self.ctx.data_changed.emit()
        return created

    def edit(self, index: int, item_id: str) -> None:
        sec = SECTIONS[index]
        tasks, suggest = self._context()
        with self.ctx.session() as s:
            obj = registry.get(s, sec.kind, item_id)
            s.expunge(obj)
        dlg = sec.dialog(obj, tasks, suggest, self.window())
        if not dlg.exec():
            return
        values = dlg.values()
        if self.ctx.run(
            lambda s: (
                registry.update(s, sec.kind, registry.get(s, sec.kind, item_id), **values)
                is not None
            ),
            self,
        ):
            self.ctx.data_changed.emit()

    def delete(self, index: int, ids: list[str]) -> None:
        sec = SECTIONS[index]
        if not ids:
            return
        what = "stavku" if len(ids) == 1 else f"{len(ids)} stavki"
        if (
            QMessageBox.question(self, "Obriši", f"Obrisati {what} iz dela „{sec.label}“?")
            != QMessageBox.StandardButton.Yes
        ):
            return

        def work(s):
            for item_id in ids:
                registry.delete(s, sec.kind, registry.get(s, sec.kind, item_id))
            return True

        if self.ctx.run(work, self):
            self.ctx.data_changed.emit()

    def _set_status(self, index: int, ids: list[str], status) -> None:
        sec = SECTIONS[index]

        def work(s):
            for item_id in ids:
                registry.update(s, sec.kind, registry.get(s, sec.kind, item_id), status=status)
            return True

        if self.ctx.run(work, self):
            self.ctx.data_changed.emit()

    def _activated(self, index: int, item: QTreeWidgetItem, col: int) -> None:
        item_id = item.data(0, ROLE_ID)
        if SECTIONS[index].key == "document" and col == 6 and item.text(6):
            open_location(item.text(6))
            return
        self.edit(index, item_id)

    def _menu(self, index: int, pos) -> None:
        tree = self.trees[index]
        item = tree.itemAt(pos)
        if item is None:
            return
        if not item.isSelected():
            tree.clearSelection()
            item.setSelected(True)
        ids = [it.data(0, ROLE_ID) for it in tree.selectedItems()]
        sec = SECTIONS[index]
        menu = QMenu(self)
        menu.addAction("Uredi…", lambda: QTimer.singleShot(0, lambda: self.edit(index, ids[0])))
        if sec.key == "document" and item.text(6):
            location = item.text(6)
            menu.addAction("Otvori", lambda: open_location(location))
            menu.addAction("Kopiraj link", lambda: QGuiApplication.clipboard().setText(location))
        statuses = {
            "risk": labels.RISK_STATUS,
            "document": labels.DOC_STATUS,
            "decision": labels.DECISION_STATUS,
        }.get(sec.key)
        if statuses:
            sub = menu.addMenu("Status")
            for value, label in statuses.items():
                sub.addAction(
                    label,
                    lambda v=value: QTimer.singleShot(0, lambda: self._set_status(index, ids, v)),
                )
        menu.addSeparator()
        menu.addAction(
            icons.icon("trash", theme.tokens().danger),
            "Obriši",
            lambda: QTimer.singleShot(0, lambda: self.delete(index, ids)),
        )
        menu.exec(tree.viewport().mapToGlobal(pos))


def open_location(location: str) -> None:
    """Otvara link u browseru ili fajl/folder u programu koji ga podrazumevano otvara."""
    location = location.strip().strip('"')
    if "://" in location or location.startswith("mailto:"):
        url = QUrl(location)
    else:
        url = QUrl.fromLocalFile(location)
    QDesktopServices.openUrl(url)
