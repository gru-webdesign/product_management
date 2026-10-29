from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Milestone
from app.services import milestones
from app.services import projects as projects_svc
from app.services.gantt_math import (
    TimeScale,
    describe_span,
    duration_days,
    header_ticks,
    make_scale,
    visible_range,
)


def test_scale_roundtrip():
    s = TimeScale(date(2026, 11, 2), 60, 38.0)
    assert s.x(date(2026, 11, 2)) == 0
    assert s.x(date(2026, 11, 4)) == 76
    assert s.x_end(date(2026, 11, 4)) == 114
    assert s.date_at(75.9) == date(2026, 11, 3)
    assert s.date_at(76) == date(2026, 11, 4)
    assert s.days_for(20) == 1 and s.days_for(18) == 0 and s.days_for(-40) == -1
    assert s.width == 60 * 38 and s.end == date(2027, 1, 1)


def test_visible_range_starts_monday_and_has_padding():
    start, end = visible_range([date(2026, 11, 12), date(2026, 11, 20)], date(2026, 11, 10))
    assert start.weekday() == 0 and start <= date(2026, 11, 3)
    assert end >= date(2026, 12, 11)
    assert (end - start).days >= 42


def test_visible_range_month_zoom_starts_first():
    start, _ = visible_range([], date(2026, 11, 10), "month")
    assert start.day == 1


def test_header_ticks_all_zooms():
    scale = make_scale([date(2026, 11, 1), date(2026, 12, 15)], date(2026, 11, 10), "day")
    top, bottom = header_ticks(scale, "day")
    assert len(bottom) == scale.days
    assert any(t.label == "novembar 2026" for t in top)
    assert bottom[0].label.startswith("P ")  # ponedeljak
    for zoom in ("week", "month"):
        scale = make_scale([date(2026, 11, 1)], date(2026, 11, 10), zoom)
        top, bottom = header_ticks(scale, zoom)
        assert top and bottom
        assert all(t.width > 0 for t in top + bottom)
        assert all(0 <= t.x <= scale.width for t in top + bottom)


def test_describe_span():
    assert duration_days(date(2026, 11, 2), date(2026, 11, 2)) == 1
    assert describe_span(date(2026, 11, 2), date(2026, 11, 4)).endswith("(3 dana)")
    assert describe_span(date(2026, 11, 2), date(2026, 11, 2)).endswith("(1 dan)")
    assert describe_span(date(2026, 11, 2), date(2026, 11, 22)).endswith("(21 dan)")


def test_milestones_service(session):
    p = projects_svc.create(session, name="P")
    m = milestones.create(session, p.id, "  Lansiranje ", date(2026, 12, 1))
    assert m.name == "Lansiranje"
    milestones.create(session, p.id, "Ranije", date(2026, 11, 1))
    assert [x.name for x in milestones.for_project(session, p.id)] == ["Ranije", "Lansiranje"]
    assert milestones.update(session, m, done=True) == ["done"]
    with pytest.raises(ValueError):
        milestones.update(session, m, name=" ")
    milestones.delete(session, m)
    assert session.get(Milestone, m.id) is None
