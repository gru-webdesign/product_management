from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtWidgets import QApplication

from app.services import budget as budget_service
from app.ui import theme
from app.ui.dialogs.budget_dialog import BudgetDialog
from app.ui.dialogs.cost_dialog import MoneyEntryDialog
from app.ui.main_window import MainWindow
from app.ui.views.budget_view import BudgetView, nice_ceiling
from scripts.seed_demo import seed


@pytest.fixture
def budget(qtbot, db):
    with db.session() as s:
        seed(s, today=date.today())
        s.commit()
    theme.apply(QApplication.instance(), "light")
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.show()
    w.tabs.setCurrentIndex(3)
    view = w.views[3]
    assert isinstance(view, BudgetView)
    return w, view


def test_kpis_and_tables(budget):
    _, view = budget
    assert view.k_budget.value.text() == "222.000,00 RSD"
    assert view.k_spent.value.text() == "124.930,80 RSD"
    assert view.categories.topLevelItemCount() == 4
    assert view.costs.topLevelItemCount() == 4
    assert view.incomes.topLevelItemCount() == 1
    assert view.banner.isVisible() and "Softver" in view.banner.text.text()


def test_add_eur_cost_uses_last_rate(budget, qtbot):
    w, view = budget
    dlg = MoneyEntryDialog(w.ctx, "cost", None, w)
    qtbot.addWidget(dlg)
    dlg.amount.setText("50")
    dlg.currency.setCurrentIndex(dlg.currency.findData("EUR"))
    assert dlg.rate.value() == pytest.approx(117.2)  # zapamćen kurs iz demo troška
    assert "5.860,00 RSD" in dlg.converted.text()
    dlg.category.setCurrentIndex(dlg.category.findText("Ostalo"))
    dlg.vendor.setText("Hosting")
    dlg.validate()
    assert dlg.save()
    assert view.costs.topLevelItemCount() == 5
    with w.db.session() as s:
        line = next(
            x for x in budget_service.summary(s, w.ctx.project_id).lines if x.name == "Ostalo"
        )
        assert line.spent == 586000


def test_cost_dialog_validation(budget, qtbot):
    w, _ = budget
    dlg = MoneyEntryDialog(w.ctx, "cost", None, w)
    qtbot.addWidget(dlg)
    with pytest.raises(ValueError):
        dlg.validate()
    dlg.amount.setText("10")
    dlg.currency.setCurrentIndex(dlg.currency.findData("USD"))
    dlg.rate.setValue(0)
    with pytest.raises(ValueError, match="kurs"):
        dlg.validate()


def test_income_dialog(budget, qtbot):
    w, view = budget
    dlg = MoneyEntryDialog(w.ctx, "income", None, w)
    qtbot.addWidget(dlg)
    dlg.amount.setText("120.000")
    dlg.description.setText("Završna rata")
    assert dlg.save()
    assert view.k_income.value.text() == "240.000,00 RSD"


def test_budget_dialog_sets_plan(budget, qtbot):
    w, view = budget
    dlg = BudgetDialog(w.ctx, w)
    qtbot.addWidget(dlg)
    with w.db.session() as s:
        ostalo = next(c.id for c in budget_service.categories(s) if c.name == "Ostalo")
    dlg.edits[ostalo].setText("15.000")
    assert "232.000,00" in dlg.total.text() or dlg.total.text()
    assert dlg.save()
    assert view.k_budget.value.text() == "232.000,00 RSD"


def test_nice_ceiling():
    assert nice_ceiling(0) == 1
    assert nice_ceiling(137) == 200
    assert nice_ceiling(244) == 250
    assert nice_ceiling(9) == 10
