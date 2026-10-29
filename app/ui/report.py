"""PDF izveštaj projekta: zaglavlje, napredak, budžet, Gant, zadaci, milestone-i i vreme.

Pravi se preko Qt-a (QTextDocument + QPdfWriter), bez dodatnih biblioteka. Gant je slika
istog grafikona koji se vidi u aplikaciji, uvek u svetloj temi da bi bio čitljiv na papiru.
"""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, Qt, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session

from app.labels import PRIORITY, PROJECT_STATUS, TASK_STATUS
from app.services import budget as budget_service
from app.services import milestones as ms_service
from app.services import projects as project_service
from app.services import tasks as task_service
from app.services import timetracking as tt
from app.services.money import format_money
from app.services.tasks import is_overdue
from app.ui import theme

INK, MUTED, LINE, ACCENT, DANGER, WARN = (
    "#18181C",
    "#5E5E68",
    "#E4E4E8",
    "#2F55D4",
    "#D23434",
    "#B8620A",
)


def gantt_image(session: Session, project_id: str) -> QImage | None:
    """Gant u nedeljnom zumu, od početka do poslednjeg datuma, u svetloj temi."""
    from app.ui.views.gantt.chart import GanttChart
    from app.ui.views.gantt.gantt_view import load_chart_data
    from app.ui.views.gantt.model import HEADER_H, ROW_H

    rows, milestones, deps, extra = load_chart_data(session, project_id)
    if not any(r.dated for r in rows) and not milestones:
        return None
    manager = theme.manager()
    previous = manager.tokens
    manager.tokens = theme.LIGHT
    try:
        chart = GanttChart()
        chart.setHorizontalScrollBarPolicy(chart.horizontalScrollBarPolicy().ScrollBarAlwaysOff)
        chart.setVerticalScrollBarPolicy(chart.verticalScrollBarPolicy().ScrollBarAlwaysOff)
        chart.set_data(rows, milestones, deps, "week", False, extra)
        # Širina do poslednjeg datuma + mesto za natpis, bez praznih nedelja posle kraja.
        last = max(
            [r.end for r in rows if r.dated] + [m.date for m in milestones],
        )
        width = int(min(chart.x_end_of(last) + 190, chart.left_w + chart.scale.width + 20))
        height = int(HEADER_H + (len(rows) + 1) * ROW_H + 6)
        # Prikaz van ekrana da bi se raspored i skrolovanje zaista primenili pre snimanja.
        chart.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        chart.resize(width, height)
        chart.show()
        QApplication.processEvents()
        chart.horizontalScrollBar().setValue(0)
        chart.verticalScrollBar().setValue(0)
        QApplication.processEvents()
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0xFFFFFFFF)
        painter = QPainter(image)
        chart.render(painter)
        painter.end()
        chart.hide()
        chart.deleteLater()
        return image
    finally:
        manager.tokens = previous


def _h(text: str) -> str:
    # Prazan red ispred: QTextDocument ne poštuje gornju marginu posle tabele.
    return (
        '<p style="font-size:8pt;margin:0;">&nbsp;</p>'
        f'<p style="font-size:12.5pt;font-weight:600;margin:0 0 8px 0;">{escape(text)}</p>'
    )


def _cell(text: str, style: str = "") -> str:
    return f'<td style="padding:5px 8px;border-bottom:1px solid {LINE};{style}">{text}</td>'


def _head(cols: list[tuple[str, str]]) -> str:
    return (
        "<tr>"
        + "".join(
            f'<th style="text-align:{align};padding:6px 8px;color:{MUTED};font-weight:600;'
            f'border-bottom:1px solid {INK};">{escape(c)}</th>'
            for c, align in cols
        )
        + "</tr>"
    )


def build_html(
    session: Session,
    project_id: str,
    with_gantt: bool,
    gantt_size: tuple[int, int] = (1000, 300),
) -> str:
    p = project_service.get(session, project_id)
    done, total, pct = project_service.progress(session, project_id)
    s = budget_service.summary(session, project_id)
    fm = lambda v: format_money(v, s.base)  # noqa: E731
    today = date.today()
    dates = ""
    if p.start_date or p.end_date:
        a = p.start_date.strftime("%d.%m.%Y.") if p.start_date else "?"
        b = p.end_date.strftime("%d.%m.%Y.") if p.end_date else "?"
        dates = f"{a} - {b}"
    meta = "&nbsp;&nbsp;&nbsp;".join(
        escape(x) for x in (p.client, PROJECT_STATUS[p.status], dates) if x
    )
    out = [
        f"""
<html><body style="font-family:'Geist','Segoe UI',sans-serif;color:{INK};font-size:9.5pt;">
<p style="margin:0;font-size:20pt;font-weight:600;">{escape(p.name)}</p>
<p style="margin:2px 0 10px 0;color:{MUTED};">{meta}</p>
<table width="100%" cellspacing="0" style="margin-bottom:12px;"><tr>
<td width="25%"><span style="color:{MUTED};">Napredak</span><br>
<span style="font-size:15pt;font-weight:600;">{pct}%</span><br>
<span style="color:{MUTED};">{done} od {total} zadataka</span></td>"""
    ]
    if s.planned:
        color = DANGER if s.state == "over" else (WARN if s.state == "warn" else INK)
        out.append(f"""<td width="25%"><span style="color:{MUTED};">Budžet</span><br>
<span style="font-size:15pt;font-weight:600;">{fm(s.planned)}</span></td>
<td width="25%"><span style="color:{MUTED};">Potrošeno</span><br>
<span style="font-size:15pt;font-weight:600;color:{color};">{fm(s.spent)}</span><br>
<span style="color:{MUTED};">{s.percent}% budžeta</span></td>
<td width="25%"><span style="color:{MUTED};">Preostalo</span><br>
<span style="font-size:15pt;font-weight:600;">{fm(s.remaining)}</span></td>""")
    out.append("</tr></table>")
    if with_gantt:
        out.append(
            _h("Gant") + f'<p style="margin:0;"><img src="gantt://chart" '
            f'width="{gantt_size[0]}" height="{gantt_size[1]}"></p>'
        )

    out.append(_h("Zadaci") + '<table width="100%" cellspacing="0">')
    out.append(
        _head(
            [
                ("Zadatak", "left"),
                ("Status", "left"),
                ("Prioritet", "left"),
                ("Početak", "left"),
                ("Rok", "left"),
                ("Progres", "right"),
                ("Utrošeno", "right"),
            ]
        )
    )
    for t, depth in task_service.tree(session, project_id):
        indent = "&nbsp;" * (4 * depth)
        weight = "font-weight:600;" if depth == 0 else ""
        late = f"color:{DANGER};" if is_overdue(t, today) else ""
        out.append(
            "<tr>"
            + "".join(
                [
                    _cell(indent + escape(t.title), weight),
                    _cell(TASK_STATUS[t.status]),
                    _cell(PRIORITY[t.priority]),
                    _cell(t.start_date.strftime("%d.%m.%Y.") if t.start_date else ""),
                    _cell(t.due_date.strftime("%d.%m.%Y.") if t.due_date else "", late),
                    _cell(f"{t.progress}%", "text-align:right;"),
                    _cell(
                        tt.format_hours(t.actual_hours) if t.actual_hours else "",
                        "text-align:right;",
                    ),
                ]
            )
            + "</tr>"
        )
    out.append("</table>")

    milestones = ms_service.for_project(session, project_id)
    if milestones:
        out.append(_h("Milestone-i") + '<table width="100%" cellspacing="0">')
        out.append(_head([("Datum", "left"), ("Naziv", "left"), ("Stanje", "left")]))
        for m in milestones:
            out.append(
                "<tr>"
                + _cell(m.date.strftime("%d.%m.%Y."))
                + _cell(escape(m.name))
                + _cell("ostvaren" if m.done else "")
                + "</tr>"
            )
        out.append("</table>")

    if s.lines:
        out.append(_h("Budžet po kategorijama") + '<table width="100%" cellspacing="0">')
        out.append(
            _head(
                [
                    ("Kategorija", "left"),
                    ("Planirano", "right"),
                    ("Potrošeno", "right"),
                    ("Preostalo", "right"),
                    ("%", "right"),
                ]
            )
        )
        for line in s.lines:
            st = s.line_state(line)
            color = DANGER if st in ("over", "unplanned") else (WARN if st == "warn" else INK)
            out.append(
                "<tr>"
                + _cell(escape(line.name))
                + _cell(fm(line.planned), "text-align:right;")
                + _cell(fm(line.spent), f"text-align:right;color:{color};")
                + _cell(fm(line.remaining), "text-align:right;")
                + _cell(f"{line.percent}%", "text-align:right;")
                + "</tr>"
            )
        out.append("</table>")
        if s.income:
            out.append(
                f'<p style="margin:8px 0 0 0;">Prihod: <b>{fm(s.income)}</b>'
                f"&nbsp;&nbsp;&nbsp;Zarada: <b>{fm(s.profit)}</b></p>"
            )

    out.append(
        f'<p style="margin-top:18px;color:{MUTED};font-size:8pt;">Izveštaj napravljen '
        f"{today.strftime('%d.%m.%Y.')} u aplikaciji Etapa.</p></body></html>"
    )
    return "".join(out)


def write_pdf(session: Session, project_id: str, path: Path) -> Path:
    image = gantt_image(session, project_id)
    doc = QTextDocument()
    if image is not None:
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl("gantt://chart"), image)
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Portrait)
    writer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Unit.Millimeter)
    writer.setResolution(144)
    writer.setTitle(project_service.get(session, project_id).name)
    writer.setCreator("Etapa")
    layout = writer.pageLayout()
    rect = layout.paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    size = (1000, 300)
    if image is not None:
        # Gant zauzima celu širinu strane, ali ne više od prirodne veličine slike.
        w = min(int(rect.width()), image.width())
        size = (w, int(w * image.height() / image.width()))
    doc.setHtml(build_html(session, project_id, image is not None, size))
    doc.setDocumentMargin(0)
    doc.print_(writer)
    return path
