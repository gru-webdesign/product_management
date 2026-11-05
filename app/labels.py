"""Srpski nazivi i boje za enum vrednosti (koriste ih UI i stranica za deljenje)."""

from __future__ import annotations

from app.db.models import (
    DecisionStatus,
    DependencyType,
    DocStatus,
    Priority,
    ProjectStatus,
    RiskKind,
    RiskStatus,
    TaskStatus,
)

TASK_STATUS = {
    TaskStatus.TODO: "Za uraditi",
    TaskStatus.IN_PROGRESS: "U toku",
    TaskStatus.REVIEW: "Na proveri",
    TaskStatus.BLOCKED: "Blokirano",
    TaskStatus.ON_HOLD: "Na čekanju",
    TaskStatus.DONE: "Završeno",
}

TASK_STATUS_COLOR = {
    TaskStatus.TODO: "#7C7C86",
    TaskStatus.IN_PROGRESS: "#2F55D4",
    TaskStatus.REVIEW: "#B8620A",
    TaskStatus.BLOCKED: "#D23434",
    TaskStatus.ON_HOLD: "#7A5AC0",
    TaskStatus.DONE: "#22844C",
}

PRIORITY = {
    Priority.LOW: "Nizak",
    Priority.MEDIUM: "Srednji",
    Priority.HIGH: "Visok",
    Priority.URGENT: "Hitno",
}

PRIORITY_COLOR = {
    Priority.LOW: "#7C7C86",
    Priority.MEDIUM: "#5E5E68",
    Priority.HIGH: "#B8620A",
    Priority.URGENT: "#D23434",
}

PROJECT_STATUS = {
    ProjectStatus.PLANNED: "Planiran",
    ProjectStatus.ACTIVE: "Aktivan",
    ProjectStatus.ON_HOLD: "Na čekanju",
    ProjectStatus.DONE: "Završen",
    ProjectStatus.CANCELLED: "Otkazan",
}

DEPENDENCY_TYPE = {
    DependencyType.FINISH_TO_START: "Završi → počni",
    DependencyType.START_TO_START: "Počni → počni",
    DependencyType.FINISH_TO_FINISH: "Završi → završi",
}

FIELD = {
    "name": "naziv",
    "title": "naziv",
    "description": "opis",
    "client": "partner / klijent",
    "color": "boja",
    "start_date": "početak",
    "end_date": "kraj",
    "due_date": "rok",
    "status": "status",
    "priority": "prioritet",
    "progress": "progres",
    "estimate_hours": "procena sati",
    "actual_hours": "utrošeni sati",
    "planned_cost_minor": "planirani trošak",
    "archived": "arhiviran",
    "parent_id": "nadređeni zadatak",
    "tags": "tagovi",
    "work_type": "vrsta rada",
    "phase": "faza",
    "owner": "nosilac",
    "project_type": "vrsta projekta",
    "sponsor": "sponzor",
    "department": "odeljenje",
    "manager": "vođa projekta",
    "kind": "vrsta",
    "probability": "verovatnoća",
    "impact": "uticaj",
    "mitigation": "mera",
    "decision": "odluka",
    "rationale": "obrazloženje",
    "approved_by": "odobrio",
    "decided_on": "datum odluke",
    "location": "lokacija",
    "version": "verzija",
    "organization": "organizacija",
    "role": "uloga",
    "raci": "RACI",
}

# --- Registar projekta ---------------------------------------------------------------------------

RISK_KIND = {
    RiskKind.RISK: "Rizik",
    RiskKind.ISSUE: "Problem",
    RiskKind.ASSUMPTION: "Pretpostavka",
    RiskKind.DEPENDENCY: "Spoljna zavisnost",
}

RISK_STATUS = {
    RiskStatus.OPEN: "Otvoren",
    RiskStatus.IN_PROGRESS: "U obradi",
    RiskStatus.ACCEPTED: "Prihvaćen",
    RiskStatus.CLOSED: "Zatvoren",
}

PROBABILITY = {1: "Niska", 2: "Srednja", 3: "Visoka", 4: "Vrlo visoka"}
IMPACT = {1: "Nizak", 2: "Srednji", 3: "Visok", 4: "Kritičan"}
LEVEL3 = {1: "Nizak", 2: "Srednji", 3: "Visok"}

RACI = {
    "R": "R: izvršava",
    "A": "A: odgovara i odobrava",
    "C": "C: konsultuje se",
    "I": "I: informiše se",
}

DOC_STATUS = {
    DocStatus.DRAFT: "Nacrt",
    DocStatus.REVIEW: "U reviziji",
    DocStatus.APPROVED: "Odobren",
    DocStatus.OBSOLETE: "Zastareo",
}

DECISION_STATUS = {
    DecisionStatus.PROPOSED: "Predložena",
    DecisionStatus.APPROVED: "Usvojena",
    DecisionStatus.REJECTED: "Odbijena",
    DecisionStatus.SUPERSEDED: "Zamenjena",
}


def risk_level(score: int) -> str:
    """Ocena rizika (verovatnoća × uticaj, 1 do 16) u reč."""
    if score >= 12:
        return "Kritičan"
    if score >= 8:
        return "Visok"
    if score >= 4:
        return "Srednji"
    return "Nizak"


# --- Predlozi za polja sa proizvoljnim unosom ---------------------------------------------------
# Nude se u padajućim listama; korisnik uvek može da upiše svoje. Ranije upisane vrednosti iz
# baze se dodaju na listu (services/suggestions.py).

PROJECT_TYPES = [
    "Onboarding partnera",
    "Novi servis ili proizvod",
    "Unapređenje postojećeg servisa",
    "Integracija sa partnerom (API)",
    "Regulatorni zahtev",
    "Usklađenost i AML",
    "Istraživanje i discovery",
    "Analitika i izveštavanje",
    "Mobilna aplikacija",
    "Web i portal",
    "Infrastruktura i bezbednost",
    "Migracija sistema",
    "Interni proces",
    "Marketing kampanja",
    "Lansiranje na tržište",
    "Ugovaranje i nabavka",
    "Obuka i edukacija",
]

WORK_TYPES = [
    "Analiza",
    "Poslovni zahtevi",
    "Specifikacija",
    "Dokumentacija",
    "Istraživanje",
    "Analitika i podaci",
    "UX i dizajn",
    "Razvoj",
    "Integracija",
    "Testiranje i QA",
    "UAT",
    "Bezbednost",
    "Usklađenost (compliance)",
    "AML i KYC",
    "Pravno i ugovori",
    "Finansije",
    "Nabavka",
    "Infrastruktura",
    "Puštanje u rad",
    "Obuka",
    "Komunikacija",
    "Marketing",
    "Podrška",
    "Sastanak",
    "Izveštavanje",
    "Odobrenje",
]

PHASES = [
    "Inicijacija",
    "Discovery i analiza",
    "Planiranje",
    "Dizajn rešenja",
    "Ugovaranje",
    "Razvoj i integracija",
    "Testiranje",
    "Pilot",
    "Puštanje u rad",
    "Stabilizacija",
    "Zatvaranje",
]

TEAMS = [
    "Product",
    "IT razvoj",
    "Backend",
    "Mobilni tim",
    "QA",
    "DevOps i infrastruktura",
    "Bezbednost informacija",
    "Compliance",
    "AML",
    "Pravna služba",
    "Finansije",
    "Računovodstvo",
    "Operacije",
    "Back office",
    "Korisnička podrška",
    "Prodaja",
    "Marketing",
    "Risk menadžment",
    "Interna revizija",
    "Uprava",
    "Partner",
    "Dobavljač",
]

DOC_KINDS = [
    "Poslovni zahtevi (BRD)",
    "Specifikacija proizvoda (PRD)",
    "Funkcionalna specifikacija",
    "Tehnička specifikacija",
    "API dokumentacija",
    "Ugovor",
    "Aneks ugovora",
    "NDA",
    "SLA",
    "Procena rizika",
    "Procena uticaja na zaštitu podataka (DPIA)",
    "Compliance analiza",
    "AML/KYC procedura",
    "Test plan",
    "Test izveštaj / UAT zapisnik",
    "Plan puštanja u rad",
    "Uputstvo za korisnike",
    "Interna procedura",
    "Prezentacija",
    "Zapisnik sa sastanka",
    "Izveštaj",
    "Analiza tržišta",
    "Ponuda",
    "Faktura",
    "Ostalo",
]

ORGANIZATIONS = ["Interno", "Partner", "Dobavljač", "Regulator", "Banka", "Klijent", "Konsultant"]


PROJECT_COLORS = [
    "#2F55D4",
    "#0E7C86",
    "#22844C",
    "#8A7A12",
    "#B8620A",
    "#C2410C",
    "#BE3455",
    "#7A5AC0",
    "#5E5E68",
]


def display_value(field: str, value) -> str:
    """Čitljiv prikaz vrednosti u istoriji izmena."""
    if value is None or value == "":
        return "prazno"
    if isinstance(value, TaskStatus):
        return TASK_STATUS[value]
    if isinstance(value, Priority):
        return PRIORITY[value]
    if isinstance(value, ProjectStatus):
        return PROJECT_STATUS[value]
    if isinstance(value, RiskKind):
        return RISK_KIND[value]
    if isinstance(value, RiskStatus):
        return RISK_STATUS[value]
    if isinstance(value, DocStatus):
        return DOC_STATUS[value]
    if isinstance(value, DecisionStatus):
        return DECISION_STATUS[value]
    if field == "probability":
        return PROBABILITY.get(int(value), str(value))
    if field == "impact":
        return IMPACT.get(int(value), str(value))
    if isinstance(value, bool):
        return "da" if value else "ne"
    if field == "planned_cost_minor":
        from app.services.money import format_money

        return format_money(int(value))
    if field == "progress":
        return f"{value}%"
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y.")
    return str(value)
