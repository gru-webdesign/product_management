from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services import budget as svc
from app.services import projects as projects_svc
from app.services import tasks as tasks_svc
from app.services.defaults import set_setting
from app.services.money import to_minor

D = date(2026, 11, 2)


@pytest.fixture
def ctx(session):
    p = projects_svc.create(session, name="P")
    cats = {c.name: c for c in svc.categories(session)}
    return p, cats


def test_planned_and_spent_by_category(session, ctx):
    p, cats = ctx
    svc.set_planned(session, p.id, cats["Rad"].id, to_minor(1000))
    svc.set_planned(session, p.id, cats["Materijal"].id, to_minor(500))
    svc.add_cost(session, p.id, on=D, amount_minor=to_minor(300), category_id=cats["Rad"].id)
    svc.add_cost(
        session,
        p.id,
        on=D,
        amount_minor=to_minor(10),
        currency="EUR",
        rate="117.2",
        category_id=cats["Materijal"].id,
        vendor=" Figma ",
    )
    s = svc.summary(session, p.id)
    rad = next(line for line in s.lines if line.name == "Rad")
    mat = next(line for line in s.lines if line.name == "Materijal")
    assert (rad.planned, rad.spent, rad.remaining, rad.percent) == (100000, 30000, 70000, 30)
    assert mat.spent == to_minor("1172")
    assert s.planned == to_minor(1500) and s.spent == to_minor(1472)
    assert s.state == "warn"  # 98% ≥ 80%
    assert svc.last_rate(session, "EUR") == Decimal("117.2")
    assert svc.costs(session, p.id)[0].vendor in ("Figma", "")


def test_states_and_warnings(session, ctx):
    p, cats = ctx
    svc.set_planned(session, p.id, cats["Rad"].id, to_minor(100))
    svc.add_cost(session, p.id, on=D, amount_minor=to_minor(120), category_id=cats["Rad"].id)
    svc.add_cost(session, p.id, on=D, amount_minor=to_minor(5), category_id=cats["Ostalo"].id)
    s = svc.summary(session, p.id)
    levels = [lvl for lvl, _ in s.warnings()]
    texts = " ".join(t for _, t in s.warnings())
    assert s.state == "over" and "over" in levels
    assert "prekoračen" in texts and "bez planiranog" in texts
    assert svc.state_for(79, 100, 80) == "ok"
    assert svc.state_for(80, 100, 80) == "warn"
    assert svc.state_for(101, 100, 80) == "over"
    assert svc.state_for(0, 0, 80) == "ok"


def test_warn_threshold_setting(session, ctx):
    p, cats = ctx
    set_setting(session, "budget_warn_percent", "50")
    svc.set_planned(session, p.id, cats["Rad"].id, to_minor(100))
    svc.add_cost(session, p.id, on=D, amount_minor=to_minor(60), category_id=cats["Rad"].id)
    assert svc.summary(session, p.id).state == "warn"


def test_income_profit_and_task_plan(session, ctx):
    p, cats = ctx
    svc.set_planned(session, p.id, cats["Rad"].id, to_minor(100))
    tasks_svc.create(session, p.id, title="t", planned_cost_minor=to_minor(150), actual_hours=4)
    set_setting(session, "default_hourly_rate_minor", str(to_minor(2500)))
    svc.add_income(session, p.id, on=D, amount_minor=to_minor(1000), description="Avans")
    svc.add_cost(session, p.id, on=D, amount_minor=to_minor(40), category_id=cats["Rad"].id)
    s = svc.summary(session, p.id)
    assert s.income == to_minor(1000) and s.profit == to_minor(960)
    assert s.labor_value == to_minor(10000)
    assert any("zadataka" in t for _, t in s.warnings())


def test_validation(session, ctx):
    p, cats = ctx
    rad = cats["Rad"].id
    with pytest.raises(ValueError):
        svc.add_cost(session, p.id, on=D, amount_minor=0, category_id=rad)
    with pytest.raises(ValueError):
        svc.add_cost(session, p.id, on=D, amount_minor=100, category_id=rad, currency="EUR", rate=0)
    with pytest.raises(ValueError):
        svc.add_cost(session, p.id, on=D, amount_minor=100, category_id=rad, currency="GBP")
    with pytest.raises(ValueError):
        svc.add_cost(session, p.id, on=D, amount_minor=100, category_id="nema")
    with pytest.raises(ValueError):
        svc.set_planned(session, p.id, rad, -1)
    other = projects_svc.create(session, name="Drugi")
    foreign = tasks_svc.create(session, other.id, title="x")
    with pytest.raises(ValueError):
        svc.add_cost(session, p.id, on=D, amount_minor=100, category_id=rad, task_id=foreign.id)


def test_update_and_delete_cost(session, ctx):
    p, cats = ctx
    c = svc.add_cost(session, p.id, on=D, amount_minor=100, category_id=cats["Rad"].id)
    svc.update_cost(
        session,
        c,
        on=D,
        amount_minor=500,
        category_id=cats["Ostalo"].id,
        currency="EUR",
        rate="100",
    )
    assert c.amount_base_minor == 50000 and c.category_id == cats["Ostalo"].id
    svc.delete_cost(session, c)
    assert svc.costs(session, p.id) == []


def test_categories(session, ctx):
    p, cats = ctx
    c = svc.create_category(session, "Marketing", "#E5484D")
    with pytest.raises(ValueError):
        svc.create_category(session, "marketing")
    svc.rename_category(session, c, "Reklame")
    svc.set_planned(session, p.id, c.id, 100)
    svc.delete_category(session, c)
    svc.add_cost(session, p.id, on=D, amount_minor=100, category_id=cats["Rad"].id)
    with pytest.raises(ValueError):
        svc.delete_category(session, cats["Rad"])


def test_spending_series(session, ctx):
    p, cats = ctx
    for day, amount in ((date(2026, 11, 3), 100), (date(2026, 11, 1), 50), (date(2026, 11, 3), 25)):
        svc.add_cost(session, p.id, on=day, amount_minor=amount, category_id=cats["Rad"].id)
    assert svc.spending_series(session, p.id) == [(date(2026, 11, 1), 50), (date(2026, 11, 3), 175)]
