"""Uvoz zadataka iz Excel tabele (.xlsx, .xls) ili CSV-a.

Tok: read_table(putanja) → plan(session, redovi) → pregled u dijalogu → apply(session, plan).
Kolone se prepoznaju po nazivu (srpski ili engleski, velika/mala slova nisu bitna), pa tabela
ne mora da bude baš u obliku šablona. Šablon sa uputstvom pravi write_template().
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import labels
from app.db.models import DependencyType, Priority, Project, Task, TaskStatus
from app.services import dependencies as dep_service
from app.services import projects as project_service
from app.services import tasks as task_service
from app.services import timetracking

# polje → kolona u šablonu i drugi nazivi pod kojima se kolona prepoznaje
COLUMNS: dict[str, tuple[str, ...]] = {
    "project": ("Projekat", "project", "projekt"),
    "title": ("Zadatak", "naziv", "naziv zadatka", "task", "title", "summary", "ime"),
    "parent": ("Deo zadatka", "nadređeni", "nadredjeni", "parent", "glavni zadatak"),
    "status": ("Status", "stanje", "state"),
    "priority": ("Prioritet", "priority"),
    "owner": ("Nosilac", "odgovoran", "zadužen", "zaduzen", "owner", "assignee", "tim"),
    "phase": ("Faza", "phase", "etapa"),
    "work_type": ("Vrsta rada", "tip", "vrsta", "type", "work type"),
    "start_date": ("Početak", "pocetak", "start", "start date", "datum početka", "od"),
    "due_date": ("Rok", "kraj", "due", "due date", "end", "end date", "datum završetka", "do"),
    "estimate_hours": ("Procena (h)", "procena", "estimate", "sati procena"),
    "actual_hours": ("Utrošeno (h)", "utrošeno", "utroseno", "sati", "spent", "time spent"),
    "progress": ("Progres (%)", "progres", "napredak", "progress", "%"),
    "planned_cost": ("Planirani trošak", "trošak", "trosak", "budžet", "budzet", "cost"),
    "tags": ("Tagovi", "tags", "oznake", "labels"),
    "depends_on": ("Zavisi od", "zavisnost", "zavisnosti", "depends on", "predecessors"),
    "description": ("Opis", "beleške", "beleske", "napomena", "description", "notes"),
}

STATUS_WORDS: dict[str, TaskStatus] = {
    **{v.casefold(): k for k, v in labels.TASK_STATUS.items()},
    **{k.value: k for k in TaskStatus},
    "to do": TaskStatus.TODO,
    "todo": TaskStatus.TODO,
    "open": TaskStatus.TODO,
    "novo": TaskStatus.TODO,
    "nije počelo": TaskStatus.TODO,
    "in progress": TaskStatus.IN_PROGRESS,
    "u radu": TaskStatus.IN_PROGRESS,
    "radi se": TaskStatus.IN_PROGRESS,
    "review": TaskStatus.REVIEW,
    "na pregledu": TaskStatus.REVIEW,
    "testiranje": TaskStatus.REVIEW,
    "blocked": TaskStatus.BLOCKED,
    "blokiran": TaskStatus.BLOCKED,
    "on hold": TaskStatus.ON_HOLD,
    "pauzirano": TaskStatus.ON_HOLD,
    "čeka": TaskStatus.ON_HOLD,
    "done": TaskStatus.DONE,
    "closed": TaskStatus.DONE,
    "završen": TaskStatus.DONE,
    "zavrseno": TaskStatus.DONE,
    "gotovo": TaskStatus.DONE,
    "urađeno": TaskStatus.DONE,
    "uradjeno": TaskStatus.DONE,
    "da": TaskStatus.DONE,
}
PRIORITY_WORDS: dict[str, Priority] = {
    **{v.casefold(): k for k, v in labels.PRIORITY.items()},
    **{k.value: k for k in Priority},
    "nizak": Priority.LOW,
    "srednji": Priority.MEDIUM,
    "normalan": Priority.MEDIUM,
    "visok": Priority.HIGH,
    "hitan": Priority.URGENT,
    "kritičan": Priority.URGENT,
    "highest": Priority.URGENT,
    "critical": Priority.URGENT,
}


@dataclass
class Row:
    """Jedan red tabele posle provere."""

    line: int
    project: str
    title: str
    parent: str = ""
    values: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    actual_hours: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class Plan:
    rows: list[Row]
    skipped: list[str]  # opis preskočenih redova (bez naziva i sl.)
    mapping: dict[str, str]  # polje → naziv kolone iz fajla
    unknown_columns: list[str]
    new_projects: list[str]

    @property
    def warnings(self) -> list[str]:
        return [f"Red {r.line}: {w}" for r in self.rows for w in r.warnings]


@dataclass
class Result:
    tasks: int
    projects: int
    dependencies: int


# --- čitanje fajla ---


def read_table(path: str | Path) -> list[list]:
    """Prvi list Excel tabele ili CSV kao lista redova (prvi red su nazivi kolona)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = _pick_sheet(wb)
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if ext == ".xls":
        try:
            import xlrd
        except ImportError as exc:  # pragma: no cover - zavisi od instalacije
            raise ValueError(
                "Za stari .xls format treba paket xlrd (pip install xlrd), "
                "ili sačuvaj tabelu kao .xlsx."
            ) from exc
        book = xlrd.open_workbook(str(path))
        sheet = book.sheet_by_index(0)
        rows = []
        for r in range(sheet.nrows):
            row = []
            for c in range(sheet.ncols):
                cell = sheet.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
                else:
                    row.append(cell.value)
            rows.append(row)
        return rows
    if ext in (".csv", ".txt"):
        raw = path.read_bytes()
        text = None
        for enc in ("utf-8-sig", "cp1250", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
        return [list(r) for r in csv.reader(text.splitlines(), dialect)]
    raise ValueError("Podržani su Excel (.xlsx, .xls) i CSV fajlovi.")


def _pick_sheet(wb):
    for ws in wb.worksheets:
        if ws.title.casefold() in ("zadaci", "tasks"):
            return ws
    return wb.worksheets[0]


# --- tumačenje vrednosti ---


def _norm(text) -> str:
    return " ".join(str(text or "").replace("\n", " ").split())


def _key(text) -> str:
    return _norm(text).casefold().rstrip(":")


def map_columns(header: list) -> tuple[dict[str, int], list[str]]:
    """Kolona → polje. Vraća {polje: indeks} i nazive kolona koje nisu prepoznate."""
    found: dict[str, int] = {}
    unknown: list[str] = []
    for i, name in enumerate(header):
        k = _key(name)
        if not k:
            continue
        for fld, names in COLUMNS.items():
            if fld not in found and k in {n.casefold() for n in names}:
                found[fld] = i
                break
        else:
            unknown.append(_norm(name))
    return found, unknown


DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%Y.", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%m/%d/%Y")


def parse_date(value) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, int | float):  # Excel serijski broj
        if 20000 < value < 80000:
            return dt.date(1899, 12, 30) + dt.timedelta(days=int(value))
        raise ValueError(f"'{value}' nije datum")
    text = _norm(value).rstrip(".") if _norm(value).count(".") > 2 else _norm(value)
    text = text.split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{value}' nije datum (npr. 15.03.2026.)")


def parse_number(value) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    t = re.sub(r"[^\d,.\-]", "", str(value))
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or ("." in t and len(t.split(".")[1]) == 3):
        t = t.replace(".", "")
    try:
        return Decimal(t)
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' nije broj") from exc


def _split(value) -> list[str]:
    return [p for p in (_norm(x) for x in re.split(r"[;,\n]", str(value or ""))) if p]


# --- plan ---


def plan(session: Session, table: list[list], default_project: str = "") -> Plan:
    """Proverava redove i pravi plan uvoza; ništa se ne upisuje u bazu.

    default_project se koristi za redove bez kolone/vrednosti Projekat.
    """
    table = [r for r in table if any(_norm(c) for c in (r or []))]
    if not table:
        raise ValueError("Tabela je prazna.")
    mapping, unknown = map_columns(table[0])
    if "title" not in mapping:
        raise ValueError(
            "Nije pronađena kolona sa nazivom zadatka. Prva vrsta treba da ima naslove kolona, "
            "a jedna od njih da se zove „Zadatak“."
        )
    header = [_norm(c) for c in table[0]]
    rows: list[Row] = []
    skipped: list[str] = []
    for n, raw in enumerate(table[1:], start=2):
        raw = list(raw) + [None] * (len(header) - len(raw))

        def get(fld, raw=raw):
            i = mapping.get(fld)
            return raw[i] if i is not None and i < len(raw) else None

        title = _norm(get("title"))
        if not title:
            skipped.append(f"Red {n}: nema naziva zadatka")
            continue
        project = _norm(get("project")) or default_project
        if not project:
            skipped.append(f"Red {n}: nije određen projekat ({title})")
            continue
        row = Row(line=n, project=project, title=title[:300], parent=_norm(get("parent")))
        v = row.values
        status = _key(get("status"))
        if status:
            if status in STATUS_WORDS:
                v["status"] = STATUS_WORDS[status]
            else:
                row.warnings.append(f"nepoznat status „{_norm(get('status'))}“, biće Za uraditi")
        pri = _key(get("priority"))
        if pri:
            if pri in PRIORITY_WORDS:
                v["priority"] = PRIORITY_WORDS[pri]
            else:
                row.warnings.append(f"nepoznat prioritet „{_norm(get('priority'))}“, biće Srednji")
        for fld in ("owner", "phase", "work_type", "description"):
            text = str(get(fld) or "").strip()
            if text:
                v[fld] = text if fld == "description" else _norm(text)
        for fld in ("start_date", "due_date"):
            try:
                d = parse_date(get(fld))
            except ValueError as exc:
                row.warnings.append(f"{labels.FIELD.get(fld, fld)}: {exc}")
                d = None
            if d:
                v[fld] = d
        if v.get("start_date") and v.get("due_date") and v["due_date"] < v["start_date"]:
            row.warnings.append("rok je pre početka, rok je izjednačen sa početkom")
            v["due_date"] = v["start_date"]
        for fld in ("estimate_hours", "actual_hours", "progress", "planned_cost"):
            try:
                num = parse_number(get(fld))
            except ValueError as exc:
                row.warnings.append(str(exc))
                num = None
            if num is None or num < 0:
                continue
            if fld == "estimate_hours":
                v["estimate_hours"] = float(num)
            elif fld == "actual_hours":
                row.actual_hours = float(num)
            elif fld == "progress":
                pct = num * 100 if 0 < num <= 1 and "." in str(get(fld)) else num
                v["progress"] = max(0, min(100, int(pct)))
            else:
                v["planned_cost_minor"] = int(num * 100)
        if v.get("status") == TaskStatus.DONE:
            v["progress"] = 100
        row.tags = [t.lstrip("#") for t in _split(get("tags"))]
        row.depends_on = _split(get("depends_on"))
        rows.append(row)

    existing = {
        p.name.casefold()
        for p in session.scalars(select(Project).where(Project.archived.is_(False)))
    }
    new_projects = sorted({r.project for r in rows if r.project.casefold() not in existing})
    _check_links(rows)
    return Plan(
        rows=rows,
        skipped=skipped,
        mapping={f: header[i] for f, i in mapping.items()},
        unknown_columns=unknown,
        new_projects=new_projects,
    )


def _check_links(rows: list[Row]) -> None:
    by_project: dict[str, set[str]] = {}
    for r in rows:
        by_project.setdefault(r.project.casefold(), set()).add(r.title.casefold())
    for r in rows:
        titles = by_project[r.project.casefold()]
        if r.parent and r.parent.casefold() not in titles:
            r.warnings.append(f"„Deo zadatka“ {r.parent} nije u tabeli, traži se u projektu")
        for d in r.depends_on:
            if d.casefold() not in titles:
                r.warnings.append(f"„Zavisi od“ {d} nije u tabeli, traži se u projektu")


# --- upis ---


def apply(session: Session, p: Plan, today: dt.date | None = None) -> Result:
    """Upisuje plan: projekti po nazivu (novi se prave), zadaci, podzadaci, zavisnosti, sati."""
    today = today or dt.date.today()
    projects: dict[str, Project] = {
        x.name.casefold(): x
        for x in session.scalars(select(Project).where(Project.archived.is_(False)))
    }
    created_projects = 0
    for name in p.new_projects:
        projects[name.casefold()] = project_service.create(session, name=name)
        created_projects += 1

    created: dict[tuple[str, str], Task] = {}
    existing_cache: dict[str, dict[str, Task]] = {}

    def lookup(project: Project, title: str) -> Task | None:
        key = (project.id, title.casefold())
        if key in created:
            return created[key]
        if project.id not in existing_cache:
            existing_cache[project.id] = {
                t.title.casefold(): t for t, _ in task_service.tree(session, project.id)
            }
        return existing_cache[project.id].get(title.casefold())

    # roditelji pre dece: red čiji roditelj je u tabeli ide posle roditelja
    pending = list(p.rows)
    ordered: list[Row] = []
    titles_in_table = {(r.project.casefold(), r.title.casefold()) for r in p.rows}
    placed: set[tuple[str, str]] = set()
    while pending:
        progress = False
        for r in list(pending):
            parent_key = (r.project.casefold(), r.parent.casefold())
            if not r.parent or parent_key not in titles_in_table or parent_key in placed:
                ordered.append(r)
                placed.add((r.project.casefold(), r.title.casefold()))
                pending.remove(r)
                progress = True
        if not progress:  # kružna veza: ostatak bez roditelja
            ordered.extend(pending)
            break

    for r in ordered:
        project = projects[r.project.casefold()]
        values = dict(r.values)
        if r.parent:
            parent = lookup(project, r.parent)
            if parent is not None and parent.title.casefold() != r.title.casefold():
                values["parent_id"] = parent.id
        task = task_service.create(
            session, project.id, title=r.title, tags=r.tags or None, **values
        )
        created[(project.id, r.title.casefold())] = task
        if r.actual_hours:
            day = values.get("due_date") or values.get("start_date") or today
            timetracking.add_entry(session, task.id, min(day, today), r.actual_hours, "Uvezeno")

    deps = 0
    for r in ordered:
        project = projects[r.project.casefold()]
        task = created[(project.id, r.title.casefold())]
        for name in r.depends_on:
            pred = lookup(project, name)
            if pred is None or pred.id == task.id:
                continue
            try:
                dep_service.add(session, pred, task, DependencyType.FINISH_TO_START, 0)
                deps += 1
            except ValueError:
                continue  # kružna ili dupla zavisnost se preskače
    session.flush()
    return Result(tasks=len(created), projects=created_projects, dependencies=deps)


# --- šablon ---

TEMPLATE_HELP = [
    (
        "Projekat",
        "Naziv projekta. Ako projekat ne postoji, napravi se pri uvozu. "
        "Može da ostane prazno ako u dijalogu izabereš projekat.",
    ),
    ("Zadatak", "Obavezno. Naziv zadatka."),
    ("Deo zadatka", "Naziv većeg zadatka kome ovaj pripada (postaje njegov korak)."),
    ("Status", "Za uraditi, U toku, Na proveri, Blokirano, Na čekanju, Završeno."),
    ("Prioritet", "Nizak, Srednji, Visok, Hitno."),
    ("Nosilac", "Osoba ili tim."),
    ("Faza", "Npr. Inicijacija, Razvoj i integracija, UAT."),
    ("Vrsta rada", "Npr. Analiza, Integracija, Dokumentacija."),
    ("Početak", "Datum, npr. 15.03.2026."),
    ("Rok", "Datum, npr. 30.03.2026."),
    ("Procena (h)", "Broj sati."),
    ("Utrošeno (h)", "Broj sati; upisuje se kao jedan unos vremena."),
    ("Progres (%)", "0 do 100. Završen zadatak dobija 100."),
    ("Planirani trošak", "Iznos u osnovnoj valuti (npr. 15000)."),
    ("Tagovi", "Odvojeno zarezom, npr. TNapp, partner."),
    ("Zavisi od", "Nazivi zadataka koji moraju biti gotovi pre ovog, odvojeni sa ;"),
    ("Opis", "Slobodan tekst."),
]


def write_template(path: str | Path) -> Path:
    """Excel šablon za uvoz: list Zadaci sa primerom i list Uputstvo."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    path = Path(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Zadaci"
    headers = [h for h, _ in TEMPLATE_HELP]
    ws.append(headers)
    example = [
        [
            "Integracija partnera X",
            "Analiza API dokumentacije",
            "",
            "Završeno",
            "Visok",
            "Backend",
            "Razvoj i integracija",
            "Integracija",
            "03.02.2026",
            "06.02.2026",
            16,
            14,
            100,
            "",
            "partner",
            "",
            "Pregled REST API-ja i sandbox-a",
        ],
        [
            "Integracija partnera X",
            "Integracija sa API-jem",
            "",
            "U toku",
            "Visok",
            "Backend",
            "Razvoj i integracija",
            "Integracija",
            "09.02.2026",
            "27.02.2026",
            60,
            20,
            40,
            200000,
            "partner",
            "Analiza API dokumentacije",
            "",
        ],
        [
            "Integracija partnera X",
            "Mapiranje kodova grešaka",
            "Integracija sa API-jem",
            "Za uraditi",
            "Srednji",
            "Backend",
            "Razvoj i integracija",
            "Integracija",
            "16.02.2026",
            "20.02.2026",
            8,
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        [
            "Integracija partnera X",
            "UAT sa partnerom",
            "",
            "Za uraditi",
            "Visok",
            "QA",
            "UAT",
            "UAT",
            "02.03.2026",
            "13.03.2026",
            24,
            "",
            "",
            "",
            "partner",
            "Integracija sa API-jem",
            "",
        ],
    ]
    for r in example:
        ws.append(r)
    bold = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="0A1128")
    for c in ws[1]:
        c.font, c.fill = bold, fill
        c.alignment = Alignment(vertical="center")
    widths = [24, 34, 26, 13, 11, 16, 22, 18, 12, 12, 11, 12, 11, 15, 18, 30, 40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "B2"
    statuses = ",".join(labels.TASK_STATUS.values())
    priorities = ",".join(labels.PRIORITY.values())
    for col, values in (("D", statuses), ("E", priorities)):
        dv = DataValidation(type="list", formula1=f'"{values}"', allow_blank=True)
        dv.showErrorMessage = False  # dozvoljen i drugi tekst; Etapa ga prijavi pri uvozu
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}2000")

    info = wb.create_sheet("Uputstvo")
    info.append(["Kolona", "Šta se upisuje"])
    for c in info[1]:
        c.font, c.fill = bold, fill
    for row in TEMPLATE_HELP:
        info.append(list(row))
    info.append([])
    info.append(
        [
            "Napomena",
            "Redosled kolona nije bitan, a nepotrebne kolone možeš da obrišeš. "
            "Primer redova obriši pre uvoza.",
        ]
    )
    info.column_dimensions["A"].width = 20
    info.column_dimensions["B"].width = 100
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
