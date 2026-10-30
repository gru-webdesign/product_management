"""Prikaz Budžet: zbirovi, upozorenja, po kategorijama, grafikon potrošnje, troškovi i prihodi."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtCore import QDateTime, QMargins, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.db.models import CostEntry, IncomeEntry
from app.services import budget as budget_service
from app.services.money import format_money
from app.ui import icons, theme
from app.ui.dialogs.budget_dialog import edit_budget
from app.ui.dialogs.cost_dialog import edit_money_entry
from app.ui.sidebar import color_dot
from app.ui.views.base import ProjectView
from app.ui.widgets.card import Card
from app.ui.widgets.kpi import KpiCard
from app.ui.widgets.paint import ProgressDelegate

ROLE_ID = Qt.ItemDataRole.UserRole
RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter


class Banner(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.hide()

    def set(self, warnings: list[tuple[str, str]]) -> None:
        if not warnings:
            self.hide()
            return
        level = "over" if any(lvl == "over" for lvl, _ in warnings) else "warn"
        self.setProperty("level", level)
        theme.repolish(self)
        self.text.setText("\n".join(f"{msg}" for _, msg in warnings))
        self.show()


def nice_ceiling(value: float) -> float:
    """Zaokruži naviše na „lep" broj (1, 2, 2.5, 5 × 10ⁿ) da oznake na osi budu okrugle."""
    import math

    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        candidate = step * 10**exp
        if candidate >= value:
            return candidate
    return 10 ** (exp + 1)


class SpendingChart(QChartView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumHeight(200)
        self.chart_ = QChart()
        self.chart_.legend().setVisible(True)
        self.chart_.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.chart_.setMargins(QMargins(4, 4, 4, 4))
        self.chart_.setBackgroundRoundness(0)
        self.setChart(self.chart_)

    def set_data(
        self,
        series: list[tuple[date, int]],
        budget: int,
        start: date | None,
        end: date | None,
        base: str,
    ) -> None:
        t = theme.tokens()
        c = self.chart_
        c.removeAllSeries()
        for axis in c.axes():
            c.removeAxis(axis)
        c.setBackgroundBrush(QColor(t.surface))
        self.setBackgroundBrush(QColor(t.surface))
        c.setPlotAreaBackgroundVisible(False)
        c.legend().setLabelColor(QColor(t.muted))

        def ms(d: date) -> float:
            return QDateTime(datetime.combine(d, time(12))).toMSecsSinceEpoch()

        days = [d for d, _ in series] + [d for d in (start, end, date.today()) if d]
        lo = min(days) - timedelta(days=2)
        hi = max(days) + timedelta(days=2)

        spent = QLineSeries()
        spent.setName("Potrošeno")
        spent.append(ms(lo), 0)
        running = 0
        for d, total in series:
            spent.append(ms(d), running / 100_000)  # stepenasto: do dana troška staro stanje
            running = total
            spent.append(ms(d), running / 100_000)
        spent.append(ms(max(hi - timedelta(days=2), date.today())), running / 100_000)
        pen = QPen(QColor(t.accent), 2.2)
        spent.setPen(pen)
        c.addSeries(spent)

        top = nice_ceiling(max(running, budget) / 100 * 1.1 / 1000)
        if budget:
            line = QLineSeries()
            line.setName("Budžet")
            line.append(ms(lo), budget / 100_000)
            line.append(ms(hi), budget / 100_000)
            bpen = QPen(QColor(t.danger), 1.4, Qt.PenStyle.DashLine)
            line.setPen(bpen)
            c.addSeries(line)

        x = QDateTimeAxis()
        x.setFormat("dd.MM.")
        x.setTickCount(6)
        x.setRange(QDateTime(datetime.combine(lo, time())), QDateTime(datetime.combine(hi, time())))
        y = QValueAxis()
        y.setRange(0, top)
        y.setLabelFormat("%.0f" if top >= 5 else "%.1f")
        y.setTickCount(5)
        y.setTitleText(f"hiljade {base}")
        small = QFont(self.font())
        small.setPointSizeF(max(7.5, small.pointSizeF() - 1))
        for axis in (x, y):
            axis.setLabelsColor(QColor(t.muted))
            axis.setLabelsFont(small)
            axis.setGridLineColor(QColor(t.grid))
            axis.setLinePenColor(QColor(t.border))
            axis.setTitleBrush(QColor(t.muted))
            axis.setTitleFont(small)
        c.addAxis(x, Qt.AlignmentFlag.AlignBottom)
        c.addAxis(y, Qt.AlignmentFlag.AlignLeft)
        for s in c.series():
            s.attachAxis(x)
            s.attachAxis(y)


class BudgetView(ProjectView):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 10, 0, 0)
        root.setSpacing(6)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 0, 8, 4)
        self.add_cost_button = QPushButton("Trošak")
        self.add_cost_button.setProperty("primary", True)
        self.add_cost_button.setIcon(icons.icon("plus", theme.tokens().primary_text))
        self.add_cost_button.clicked.connect(lambda: self._edit("cost"))
        add_income = QPushButton("Prihod")
        add_income.setIcon(icons.icon("plus"))
        add_income.clicked.connect(lambda: self._edit("income"))
        edit_plan = QPushButton("Uredi budžet")
        edit_plan.setIcon(icons.icon("wallet"))
        edit_plan.clicked.connect(self._edit_budget)
        for b in (self.add_cost_button, add_income, edit_plan):
            bar.addWidget(b)
        bar.addStretch(1)
        self.base_label = QLabel()
        self.base_label.setProperty("faint", True)
        bar.addWidget(self.base_label)
        root.addLayout(bar)

        kpis = QGridLayout()
        kpis.setSpacing(2)
        self.k_budget = KpiCard("Budžet", "wallet", small=True)
        self.k_spent = KpiCard("Potrošeno", "coins", "warning", small=True)
        self.k_left = KpiCard("Preostalo", "hourglass", small=True)
        self.k_income = KpiCard("Prihod", "download", "success", small=True)
        self.k_profit = KpiCard("Zarada", "chart", "success", small=True)
        for i, k in enumerate(
            (self.k_budget, self.k_spent, self.k_left, self.k_income, self.k_profit)
        ):
            kpis.addWidget(k, 0, i)
        root.addLayout(kpis)

        self.banner = Banner()
        banner_wrap = QHBoxLayout()
        banner_wrap.setContentsMargins(8, 0, 8, 2)
        banner_wrap.addWidget(self.banner)
        root.addLayout(banner_wrap)

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        top = QWidget()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)
        self.categories = QTreeWidget()
        self.categories.setHeaderLabels(["Kategorija", "Planirano", "Potrošeno", "Preostalo", ""])
        self.categories.setRootIsDecorated(False)
        self.categories.setItemDelegateForColumn(4, ProgressDelegate(self.categories))
        h = self.categories.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, w in ((1, 120), (2, 120), (3, 120), (4, 120)):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.categories.setColumnWidth(col, w)
        self.categories.itemDoubleClicked.connect(
            lambda *_: QTimer.singleShot(0, self._edit_budget)
        )
        cat_card = Card("Budžet po kategorijama", icon="wallet", padding=(14, 14, 14, 8))
        cat_card.body.addWidget(self.categories)
        tl.addWidget(cat_card, 3)
        chart_card = Card("Potrošnja kroz vreme", icon="chart", padding=(10, 14, 10, 6))
        self.chart = SpendingChart()
        chart_card.body.addWidget(self.chart)
        tl.addWidget(chart_card, 2)
        split.addWidget(top)

        self.entries = QTabWidget()
        self.entries.setDocumentMode(True)
        self.costs = self._entries_tree(
            ["Datum", "Opis", "Kategorija", "Zadatak", "Iznos", "U osnovnoj valuti"], "cost"
        )
        self.incomes = self._entries_tree(["Datum", "Opis", "Iznos", "U osnovnoj valuti"], "income")
        self.entries.addTab(self.costs, "Troškovi")
        self.entries.addTab(self.incomes, "Prihodi")
        entries_card = Card(padding=(10, 8, 10, 8))
        entries_card.body.addWidget(self.entries)
        split.addWidget(entries_card)
        split.setSizes([320, 280])
        root.addWidget(split, 1)

    def _entries_tree(self, headers: list[str], kind: str) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setRootIsDecorated(False)
        tree.setSortingEnabled(False)
        h = tree.header()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tree.setColumnWidth(0, 100)
        for col in range(2, len(headers)):
            tree.setColumnWidth(col, 140)
        tree.itemDoubleClicked.connect(
            lambda item, _c, k=kind: self._edit_later(k, item.data(0, ROLE_ID))
        )
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(
            lambda pos, t=tree, k=kind: self._entry_menu(t, k, pos)
        )
        return tree

    # --- punjenje --------------------------------------------------------------------------------

    def reload(self) -> None:
        t = theme.tokens()
        pid = self.ctx.project_id
        with self.ctx.session() as s:
            summ = budget_service.summary(s, pid)
            series = budget_service.spending_series(s, pid)
            from app.services import projects as project_service

            p = project_service.get(s, pid)
            start, end = (p.start_date, p.end_date) if p else (None, None)
            cost_rows = [
                (
                    c.id,
                    c.date,
                    c.vendor or c.note or "Bez opisa",
                    c.category.name,
                    c.category.color,
                    c.task.title if c.task else "",
                    c.amount_minor,
                    c.currency,
                    c.amount_base_minor,
                )
                for c in budget_service.costs(s, pid)
            ]
            income_rows = [
                (
                    i.id,
                    i.date,
                    i.description or "Bez opisa",
                    i.amount_minor,
                    i.currency,
                    i.amount_base_minor,
                )
                for i in budget_service.incomes(s, pid)
            ]
        base = summ.base
        fm = lambda v: format_money(v, base)  # noqa: E731
        state_color = {"over": t.danger, "warn": t.warning}.get(summ.state)
        self.base_label.setText(f"Iznosi u {base} · upozorenje na {summ.warn_percent}% budžeta")
        self.k_budget.set(
            fm(summ.planned) if summ.planned else "nije postavljen",
            f"zadaci planiraju {fm(summ.tasks_planned)}" if summ.tasks_planned else "",
        )
        self.k_spent.set(
            fm(summ.spent),
            f"{summ.percent}% budžeta" if summ.planned else f"{len(cost_rows)} troškova",
            state_color,
        )
        self.k_left.set(
            fm(summ.remaining) if summ.planned else "-",
            "prekoračeno" if summ.remaining < 0 else "",
            t.danger if summ.remaining < 0 else None,
        )
        self.k_income.set(fm(summ.income), f"{len(income_rows)} uplata" if income_rows else "")
        labor = f"rad po satnici: {fm(summ.labor_value)}" if summ.labor_value else ""
        self.k_profit.set(
            fm(summ.profit),
            labor,
            t.success if summ.profit > 0 else (t.danger if summ.profit < 0 else None),
        )
        self.banner.set(summ.warnings())

        self.categories.clear()
        for line in summ.lines:
            item = QTreeWidgetItem(
                [
                    line.name,
                    fm(line.planned) if line.planned else "nije planirano",
                    fm(line.spent),
                    fm(line.remaining) if line.planned else "",
                    "",
                ]
            )
            item.setIcon(0, color_dot(line.color))
            for col in (1, 2, 3):
                item.setTextAlignment(col, RIGHT)
            st = summ.line_state(line)
            item.setData(4, ProgressDelegate.VALUE_ROLE, min(line.percent, 999))
            bar_color = {"over": t.danger, "unplanned": t.danger, "warn": t.warning}.get(st)
            if bar_color:
                item.setData(4, ProgressDelegate.COLOR_ROLE, bar_color)
            if st in ("over", "unplanned"):
                item.setForeground(2, QColor(t.danger))
            elif st == "warn":
                item.setForeground(2, QColor(t.warning))
            if line.remaining < 0 and line.planned:
                item.setForeground(3, QColor(t.danger))
            for col in (1, 2, 3):
                item.setFont(col, theme.mono(self.categories.font(), -0.5))
            self.categories.addTopLevelItem(item)
        if not summ.lines:
            empty = QTreeWidgetItem(
                ["Još nema budžeta ni troškova. Dodaj ih dugmetom „Uredi budžet“ ili „Trošak“."]  # noqa: E501
            )
            empty.setForeground(0, QColor(t.faint))
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.categories.addTopLevelItem(empty)
            self.categories.setFirstColumnSpanned(0, self.categories.rootIndex(), True)

        self.chart.set_data(series, summ.planned, start, end, base)

        self.costs.clear()
        for cid, d, desc, cat, color, task, amount, cur, base_amount in cost_rows:
            item = QTreeWidgetItem(
                [
                    d.strftime("%d.%m.%Y."),
                    desc,
                    cat,
                    task,
                    format_money(amount, cur),
                    fm(base_amount),
                ]
            )
            item.setData(0, ROLE_ID, cid)
            item.setIcon(2, color_dot(color))
            for col in (4, 5):
                item.setTextAlignment(col, RIGHT)
            if cur == base:
                item.setForeground(4, QColor(t.faint))
            for col in (0, 4, 5):
                item.setFont(col, theme.mono(self.costs.font(), -0.5))
            self.costs.addTopLevelItem(item)
        self.incomes.clear()
        for iid, d, desc, amount, cur, base_amount in income_rows:
            item = QTreeWidgetItem(
                [d.strftime("%d.%m.%Y."), desc, format_money(amount, cur), fm(base_amount)]
            )
            item.setData(0, ROLE_ID, iid)
            for col in (2, 3):
                item.setTextAlignment(col, RIGHT)
            for col in (0, 2, 3):
                item.setFont(col, theme.mono(self.incomes.font(), -0.5))
            self.incomes.addTopLevelItem(item)
        self.entries.setTabText(0, f"Troškovi ({len(cost_rows)})")
        self.entries.setTabText(1, f"Prihodi ({len(income_rows)})")

    # --- akcije ----------------------------------------------------------------------------------

    def _edit(self, kind: str, entry_id: str | None = None) -> None:
        edit_money_entry(self.ctx, kind, entry_id, self.window())

    def _edit_later(self, kind: str, entry_id: str | None) -> None:
        if entry_id:
            QTimer.singleShot(0, lambda: self._edit(kind, entry_id))

    def _edit_budget(self) -> None:
        edit_budget(self.ctx, self.window())

    def _entry_menu(self, tree: QTreeWidget, kind: str, pos) -> None:
        item = tree.itemAt(pos)
        if not item:
            return
        eid = item.data(0, ROLE_ID)
        menu = QMenu(self)
        menu.addAction(icons.icon("edit"), "Uredi…", lambda: self._edit(kind, eid))
        menu.addAction(icons.icon("trash"), "Obriši", lambda: self._delete(kind, eid))
        menu.exec(tree.viewport().mapToGlobal(pos))

    def _delete(self, kind: str, entry_id: str) -> None:
        label = "trošak" if kind == "cost" else "prihod"
        if (
            QMessageBox.question(self.window(), "Obriši", f"Obrisati {label}?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        if kind == "cost":
            self.ctx.run(lambda s: budget_service.delete_cost(s, s.get(CostEntry, entry_id)))
        else:
            self.ctx.run(lambda s: budget_service.delete_income(s, s.get(IncomeEntry, entry_id)))
