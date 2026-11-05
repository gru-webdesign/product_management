"""Predlozi za polja sa proizvoljnim unosom.

Svako polje ima svoju listu (ugrađenu, ili onu koju je korisnik uredio u Podešavanja → Liste) i
uz nju vrednosti koje su već upisane u bazu. Vrednost koju je korisnik uklonio iz liste se više ne
nudi, čak i ako je ranije upisana negde u bazi.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import labels
from app.db.models import Project, ProjectDocument, Risk, Stakeholder, Task
from app.services.defaults import get_setting, set_setting


@dataclass(frozen=True)
class ListInfo:
    key: str
    title: str
    hint: str
    columns: list = field(default_factory=list)
    builtin: tuple[str, ...] = ()


LISTS: dict[str, ListInfo] = {
    info.key: info
    for info in (
        ListInfo(
            "client",
            "Partneri i klijenti",
            "Polje Partner / klijent u projektu.",
            [Project.client],
        ),
        ListInfo(
            "organization",
            "Organizacije",
            "Organizacija zainteresovane strane (regulator, banke, dobavljači...).",
            [Stakeholder.organization, Project.client],
            tuple(labels.ORGANIZATIONS),
        ),
        ListInfo(
            "people",
            "Ljudi i timovi",
            "Nosilac zadatka, rizika i dokumenta, sponzor, vođa projekta, odeljenje.",
            [
                Task.owner,
                Risk.owner,
                ProjectDocument.owner,
                Project.department,
                Project.sponsor,
                Project.manager,
                Stakeholder.name,
            ],
            tuple(labels.TEAMS),
        ),
        ListInfo(
            "project_type",
            "Vrste projekata",
            "Vrsta projekta.",
            [Project.project_type],
            tuple(labels.PROJECT_TYPES),
        ),
        ListInfo("phase", "Faze", "Faza zadatka.", [Task.phase], tuple(labels.PHASES)),
        ListInfo(
            "work_type",
            "Vrste rada",
            "Vrsta rada na zadatku.",
            [Task.work_type],
            tuple(labels.WORK_TYPES),
        ),
        ListInfo(
            "doc_kind",
            "Vrste dokumenata",
            "Vrsta dokumenta u Registru.",
            [ProjectDocument.kind],
            tuple(labels.DOC_KINDS),
        ),
    )
}


def _key(name: str) -> str:
    return f"list.{name}"


def _clean(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = " ".join(str(item).split())
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


def _stored(session: Session, name: str) -> dict | None:
    raw = get_setting(session, _key(name))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def used_values(session: Session, name: str) -> set[str]:
    """Vrednosti tog polja koje su već upisane negde u bazi."""
    used: set[str] = set()
    for column in LISTS[name].columns:
        used.update(" ".join(v.split()) for v in session.scalars(select(column).distinct()) if v)
    used.discard("")
    return used


def is_custom(session: Session, name: str) -> bool:
    return _stored(session, name) is not None


def get_list(session: Session, name: str) -> list[str]:
    """Lista kakvu korisnik vidi u Podešavanjima: uređena (ili ugrađena) + upisane vrednosti."""
    stored = _stored(session, name)
    items = _clean(stored.get("items", [])) if stored else list(LISTS[name].builtin)
    hidden = {h.casefold() for h in (stored or {}).get("hidden", [])}
    known = {i.casefold() for i in items}
    extra = sorted(
        (v for v in used_values(session, name) if v.casefold() not in known | hidden),
        key=str.casefold,
    )
    return [*items, *extra]


def set_list(session: Session, name: str, items: list[str]) -> list[str]:
    """Čuva listu tačno ovim redom. Upisane vrednosti koje su izbačene se više ne predlažu."""
    items = _clean(items)
    keep = {i.casefold() for i in items}
    hidden = sorted(
        (v for v in used_values(session, name) if v.casefold() not in keep), key=str.casefold
    )
    set_setting(
        session, _key(name), json.dumps({"items": items, "hidden": hidden}, ensure_ascii=False)
    )
    return items


def reset_list(session: Session, name: str) -> None:
    """Vraća ugrađenu listu (sa svim upisanim vrednostima)."""
    set_setting(session, _key(name), "")


def for_field(session: Session, name: str) -> list[str]:
    """Predlozi za padajuću listu polja."""
    return get_list(session, name)
