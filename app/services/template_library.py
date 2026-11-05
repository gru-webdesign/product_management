"""Ugrađeni šabloni za product menadžment u platnoj instituciji.

Šablon se piše po fazama. Faza je niz koraka, a korak je jedan zadatak ili više zadataka koji
idu paralelno. Iz toga se sami računaju datumi (pomeraj od početka projekta), zavisnosti
(svaki korak čeka najduži zadatak prethodnog koraka) i nadređeni zadatak za svaku fazu.
"""

from __future__ import annotations

from app.db.models import DocStatus, RiskKind
from app.services.money import to_minor


def T(  # noqa: N802 (kratko ime čini šablone čitljivim)
    title: str,
    days: int,
    estimate: float | None,
    owner: str,
    work_type: str,
    priority: str = "medium",
    tags: tuple[str, ...] = (),
) -> dict:
    return {
        "title": title,
        "days": days,
        "estimate": estimate,
        "owner": owner,
        "work_type": work_type,
        "priority": priority,
        "tags": list(tags),
    }


def build(
    phases: list[tuple[str, list]],
    milestones: list[tuple[str, str]],
    budget: dict[str, int],
    risks: list[dict] = (),
    stakeholders: list[dict] = (),
    documents: list[dict] = (),
) -> dict:
    """phases = [(naziv faze, [korak, ...])], korak = zadatak (dict) ili lista paralelnih."""
    tasks: list[dict] = []
    deps: list[list[int]] = []
    ends: dict[str, int] = {}  # naziv zadatka → poslednji dan (pomeraj)
    cursor = 0
    previous: int | None = None  # indeks najdužeg zadatka prethodnog koraka
    for number, (phase, steps) in enumerate(phases, 1):
        parent_index = len(tasks)
        tasks.append(
            {
                "title": f"{number}. {phase}",
                "offset": cursor,
                "days": 1,
                "estimate": None,
                "priority": "medium",
                "parent": None,
                "tags": [],
                "phase": phase,
                "owner": "",
                "work_type": "",
            }
        )
        phase_start = cursor
        for step in steps:
            group = step if isinstance(step, list) else [step]
            longest, longest_days = None, -1
            for spec in group:
                index = len(tasks)
                tasks.append({**spec, "offset": cursor, "parent": parent_index, "phase": phase})
                ends[spec["title"]] = cursor + spec["days"] - 1
                if previous is not None:
                    deps.append([previous, index])
                if spec["days"] > longest_days:
                    longest, longest_days = index, spec["days"]
            cursor += longest_days
            previous = longest
        tasks[parent_index]["days"] = max(1, cursor - phase_start)
    return {
        "tasks": tasks,
        "deps": deps,
        "milestones": [{"name": name, "offset": ends[after]} for name, after in milestones],
        "budget": budget,
        "risks": list(risks),
        "stakeholders": list(stakeholders),
        "documents": list(documents),
    }


def R(kind: RiskKind, title: str, p: int, i: int, owner: str, mitigation: str) -> dict:  # noqa: N802
    return {
        "kind": kind.value,
        "title": title,
        "probability": p,
        "impact": i,
        "owner": owner,
        "mitigation": mitigation,
    }


def S(
    name: str,
    organization: str,
    role: str,
    raci: str,
    influence: int = 2,  # noqa: N802
    interest: int = 2,
) -> dict:
    return {
        "name": name,
        "organization": organization,
        "role": role,
        "raci": raci,
        "influence": influence,
        "interest": interest,
    }


def D(title: str, kind: str, owner: str, status: DocStatus = DocStatus.DRAFT) -> dict:  # noqa: N802
    return {"title": title, "kind": kind, "owner": owner, "status": status.value}


RISK, ISSUE, ASSUMPTION, DEPENDENCY = (
    RiskKind.RISK,
    RiskKind.ISSUE,
    RiskKind.ASSUMPTION,
    RiskKind.DEPENDENCY,
)

# --- Onboarding partnera -------------------------------------------------------------------------

ONBOARDING = build(
    [
        (
            "Inicijacija",
            [
                T(
                    "Početni sastanak sa partnerom i obim saradnje",
                    2,
                    4,
                    "Product",
                    "Sastanak",
                    "high",
                    ("partner",),
                ),
                [
                    T("Prikupljanje osnovnih podataka o partneru", 3, 4, "Product", "Analiza"),
                    T("Interni kick-off i imenovanje nosilaca", 1, 2, "Product", "Sastanak"),
                ],
                T(
                    "Poslovni slučaj: obim, prihodi, troškovi, rokovi",
                    3,
                    8,
                    "Product",
                    "Poslovni zahtevi",
                    "high",
                ),
            ],
        ),
        (
            "Due diligence i usklađenost",
            [
                [
                    T(
                        "KYB dokumentacija partnera (izvodi, vlasnička struktura)",
                        5,
                        6,
                        "Compliance",
                        "AML i KYC",
                        "high",
                        ("partner",),
                    ),
                    T(
                        "Procena IT bezbednosti partnera (upitnik)",
                        5,
                        6,
                        "Bezbednost informacija",
                        "Bezbednost",
                    ),
                ],
                [
                    T("AML procena rizika partnera", 3, 8, "AML", "AML i KYC", "high"),
                    T(
                        "Provera sankcionih lista i stvarnih vlasnika",
                        1,
                        2,
                        "AML",
                        "AML i KYC",
                        "high",
                    ),
                ],
                T("Odobrenje Compliance-a za saradnju", 2, 2, "Compliance", "Odobrenje", "urgent"),
            ],
        ),
        (
            "Ugovaranje",
            [
                [
                    T(
                        "Komercijalni uslovi, provizije i tarife",
                        4,
                        6,
                        "Prodaja",
                        "Finansije",
                        "high",
                    ),
                    T(
                        "NDA i razmena poverljivih informacija",
                        2,
                        2,
                        "Pravna služba",
                        "Pravno i ugovori",
                    ),
                ],
                T(
                    "Nacrt ugovora o saradnji i SLA",
                    5,
                    12,
                    "Pravna služba",
                    "Pravno i ugovori",
                    "high",
                ),
                T(
                    "Pregovori i usaglašavanje ugovora sa partnerom",
                    5,
                    8,
                    "Product",
                    "Pravno i ugovori",
                    "high",
                    ("partner",),
                ),
                T("Potpisivanje ugovora", 2, 2, "Uprava", "Odobrenje", "urgent"),
            ],
        ),
        (
            "Tehnička integracija",
            [
                T(
                    "Razmena API dokumentacije i pristupa test okruženju",
                    3,
                    4,
                    "IT razvoj",
                    "Integracija",
                    "high",
                    ("partner",),
                ),
                [
                    T(
                        "Razvoj integracije (slanje, isplata, statusi)",
                        15,
                        80,
                        "Backend",
                        "Razvoj",
                        "high",
                    ),
                    T(
                        "Podešavanje okruženja, VPN i sertifikata",
                        4,
                        10,
                        "DevOps i infrastruktura",
                        "Infrastruktura",
                    ),
                ],
                [
                    T("Interno testiranje integracije", 5, 24, "QA", "Testiranje i QA"),
                    T(
                        "Bezbednosni pregled integracije",
                        3,
                        8,
                        "Bezbednost informacija",
                        "Bezbednost",
                    ),
                ],
                T("UAT sa partnerom i zapisnik", 5, 16, "QA", "UAT", "high", ("partner",)),
            ],
        ),
        (
            "Operativna priprema",
            [
                [
                    T(
                        "Podešavanje partnera u sistemu: šifarnici, limiti, provizije",
                        3,
                        6,
                        "Operacije",
                        "Puštanje u rad",
                    ),
                    T(
                        "Procedura poravnanja i obračuna sa partnerom",
                        4,
                        8,
                        "Finansije",
                        "Finansije",
                    ),
                    T(
                        "Ažuriranje AML pravila i scenarija praćenja",
                        4,
                        8,
                        "AML",
                        "Usklađenost (compliance)",
                    ),
                ],
                [
                    T("Obuka operatera i korisničke podrške", 2, 8, "Korisnička podrška", "Obuka"),
                    T("Interna procedura i uputstvo za rad", 3, 6, "Operacije", "Dokumentacija"),
                ],
            ],
        ),
        (
            "Puštanje u rad",
            [
                T("Go-live odluka (checklista spremnosti)", 1, 2, "Uprava", "Odobrenje", "urgent"),
                T(
                    "Pilot sa ograničenim obimom transakcija",
                    7,
                    10,
                    "Product",
                    "Puštanje u rad",
                    "high",
                ),
                [
                    T("Puštanje u punu produkciju", 1, 4, "IT razvoj", "Puštanje u rad", "high"),
                    T("Komunikacija ka mreži i korisnicima", 3, 6, "Marketing", "Komunikacija"),
                ],
            ],
        ),
        (
            "Stabilizacija i zatvaranje",
            [
                T("Praćenje transakcija, incidenata i reklamacija", 14, 12, "Operacije", "Podrška"),
                T("Izveštaj o pokretanju i naučene lekcije", 2, 6, "Product", "Izveštavanje"),
            ],
        ),
    ],
    milestones=[
        ("Compliance odobrio saradnju", "Odobrenje Compliance-a za saradnju"),
        ("Ugovor potpisan", "Potpisivanje ugovora"),
        ("UAT završen", "UAT sa partnerom i zapisnik"),
        ("Go-live", "Puštanje u punu produkciju"),
    ],
    budget={
        "Interni rad": to_minor(900000),
        "Pravne usluge": to_minor(150000),
        "Bezbednost i testiranje": to_minor(120000),
        "Obuke": to_minor(40000),
        "Ostalo": to_minor(50000),
    },
    risks=[
        R(
            RISK,
            "Partner kasni sa KYB dokumentacijom",
            3,
            3,
            "Compliance",
            "Spisak dokumenata poslati prvog dana, rok u ugovoru o NDA, nedeljni podsetnik.",
        ),
        R(
            RISK,
            "Partner ne ispunjava AML zahteve",
            2,
            4,
            "AML",
            "Rana procena rizika pre ugovaranja; dodatne mere ili odustajanje.",
        ),
        R(
            RISK,
            "Kašnjenje API dokumentacije ili test okruženja partnera",
            3,
            3,
            "IT razvoj",
            "Dogovoriti datume u ugovoru; mock servis za razvoj.",
        ),
        R(
            RISK,
            "Neusaglašeni komercijalni uslovi produžavaju pregovore",
            2,
            3,
            "Prodaja",
            "Unapred definisan minimum i ovlašćenja za odlučivanje.",
        ),
        R(
            DEPENDENCY,
            "Saglasnost ili obaveštavanje regulatora (NBS), ako je potrebno",
            2,
            4,
            "Compliance",
            "Proveriti obavezu na početku i uključiti rok u plan.",
        ),
        R(
            ASSUMPTION,
            "Partner ima stabilno produkciono okruženje i podršku 24/7",
            2,
            3,
            "Product",
            "Potvrditi kroz SLA i bezbednosni upitnik.",
        ),
    ],
    stakeholders=[
        S("Uprava", "Interno", "Sponzor projekta", "A", 3, 2),
        S("Product menadžer", "Interno", "Vođa projekta", "R", 3, 3),
        S("Compliance i AML", "Interno", "Procena i odobrenje partnera", "A", 3, 3),
        S("Pravna služba", "Interno", "Ugovor, NDA, SLA", "C", 2, 2),
        S("IT razvoj", "Interno", "Integracija", "R", 2, 3),
        S("Finansije", "Interno", "Provizije, poravnanje", "C", 2, 2),
        S("Operacije", "Interno", "Podešavanje i svakodnevni rad", "R", 2, 3),
        S("Korisnička podrška", "Interno", "Podrška korisnicima", "I", 1, 2),
        S("Kontakt osoba kod partnera", "Partner", "Koordinacija sa partnerom", "C", 2, 3),
    ],
    documents=[
        D("KYB dokumentacija partnera", "AML/KYC procedura", "Compliance"),
        D("AML procena rizika partnera", "Procena rizika", "AML"),
        D("NDA", "NDA", "Pravna služba"),
        D("Ugovor o saradnji", "Ugovor", "Pravna služba"),
        D("SLA", "SLA", "Pravna služba"),
        D("Tehnička specifikacija integracije", "Tehnička specifikacija", "IT razvoj"),
        D("UAT zapisnik", "Test izveštaj / UAT zapisnik", "QA"),
        D("Plan puštanja u rad i go-live checklista", "Plan puštanja u rad", "Product"),
        D("Operativna procedura za partnera", "Interna procedura", "Operacije"),
    ],
)

# --- Novi servis u aplikaciji (TNapp) ------------------------------------------------------------

NEW_SERVICE = build(
    [
        (
            "Discovery",
            [
                [
                    T(
                        "Analiza potreba korisnika (intervjui, podrška, podaci)",
                        5,
                        16,
                        "Product",
                        "Istraživanje",
                        "high",
                    ),
                    T("Analiza konkurencije i tržišta", 4, 8, "Product", "Istraživanje"),
                ],
                T("Poslovni slučaj, ciljevi i KPI", 3, 8, "Product", "Poslovni zahtevi", "high"),
                T("Odobrenje koncepta", 1, 2, "Uprava", "Odobrenje", "urgent"),
            ],
        ),
        (
            "Zahtevi i dizajn rešenja",
            [
                [
                    T("Poslovni zahtevi (BRD)", 5, 16, "Product", "Poslovni zahtevi", "high"),
                    T(
                        "Regulatorna i compliance analiza servisa",
                        5,
                        10,
                        "Compliance",
                        "Usklađenost (compliance)",
                        "high",
                    ),
                ],
                [
                    T(
                        "Specifikacija proizvoda i korisničke priče (PRD)",
                        5,
                        16,
                        "Product",
                        "Specifikacija",
                        "high",
                    ),
                    T(
                        "Procena uticaja na zaštitu podataka (DPIA)",
                        3,
                        6,
                        "Bezbednost informacija",
                        "Bezbednost",
                    ),
                ],
                [
                    T("UX tok i dizajn ekrana", 7, 32, "Product", "UX i dizajn", "high"),
                    T("Tehnička arhitektura i procena", 5, 16, "IT razvoj", "Analiza", "high"),
                ],
                T("Odobrenje specifikacije i dizajna", 2, 3, "Product", "Odobrenje", "urgent"),
            ],
        ),
        (
            "Razvoj",
            [
                [
                    T("Backend API i poslovna logika", 15, 90, "Backend", "Razvoj", "high"),
                    T(
                        "Mobilna aplikacija (iOS i Android)",
                        15,
                        100,
                        "Mobilni tim",
                        "Razvoj",
                        "high",
                    ),
                    T("Admin panel i izveštaji", 8, 32, "IT razvoj", "Razvoj"),
                ],
                [
                    T(
                        "Integracija sa procesorom ili partnerom",
                        6,
                        30,
                        "Backend",
                        "Integracija",
                        "high",
                    ),
                    T(
                        "Logovanje, monitoring i alarmi",
                        3,
                        10,
                        "DevOps i infrastruktura",
                        "Infrastruktura",
                    ),
                ],
            ],
        ),
        (
            "Testiranje",
            [
                [
                    T(
                        "Funkcionalno testiranje i regresija",
                        7,
                        40,
                        "QA",
                        "Testiranje i QA",
                        "high",
                    ),
                    T(
                        "Bezbednosni (penetracioni) test",
                        5,
                        16,
                        "Bezbednost informacija",
                        "Bezbednost",
                        "high",
                    ),
                ],
                T("UAT sa poslovnim korisnicima", 4, 16, "Product", "UAT", "high"),
                T("Ispravke nalaza i finalna provera", 4, 20, "IT razvoj", "Razvoj"),
            ],
        ),
        (
            "Priprema lansiranja",
            [
                [
                    T("Uputstva, FAQ i tekstovi u aplikaciji", 4, 8, "Product", "Dokumentacija"),
                    T("Obuka korisničke podrške", 2, 6, "Korisnička podrška", "Obuka"),
                    T("Marketing plan i kampanja za lansiranje", 5, 12, "Marketing", "Marketing"),
                    T(
                        "Objava u App Store i Google Play (review)",
                        4,
                        4,
                        "Mobilni tim",
                        "Puštanje u rad",
                        "high",
                    ),
                ],
                T("Go/No-go sastanak", 1, 2, "Uprava", "Odobrenje", "urgent"),
            ],
        ),
        (
            "Lansiranje i praćenje",
            [
                T("Postepeno puštanje (deo korisnika)", 5, 6, "Product", "Puštanje u rad", "high"),
                T("Puštanje svim korisnicima", 1, 3, "IT razvoj", "Puštanje u rad", "high"),
                T(
                    "Praćenje KPI i povratnih informacija (30 dana)",
                    30,
                    16,
                    "Product",
                    "Analitika i podaci",
                ),
                T("Retrospektiva i plan sledeće verzije", 2, 4, "Product", "Sastanak"),
            ],
        ),
    ],
    milestones=[
        ("Koncept odobren", "Odobrenje koncepta"),
        ("Specifikacija odobrena", "Odobrenje specifikacije i dizajna"),
        ("Razvoj završen", "Integracija sa procesorom ili partnerom"),
        ("Go/No-go", "Go/No-go sastanak"),
        ("Dostupno svim korisnicima", "Puštanje svim korisnicima"),
    ],
    budget={
        "Interni rad": to_minor(2400000),
        "Razvoj kod dobavljača": to_minor(600000),
        "Bezbednost i testiranje": to_minor(250000),
        "Marketing": to_minor(300000),
        "Softver i licence": to_minor(60000),
        "Ostalo": to_minor(80000),
    },
    risks=[
        R(
            RISK,
            "Regulatorni zahtevi menjaju obim servisa",
            2,
            4,
            "Compliance",
            "Compliance analiza pre specifikacije; rezerva u planu.",
        ),
        R(
            RISK,
            "Nalazi penetracionog testa odlažu lansiranje",
            3,
            3,
            "Bezbednost informacija",
            "Bezbednosni pregled arhitekture rano; vreme za ispravke.",
        ),
        R(
            RISK,
            "Odbijanje ili kašnjenje review-a u App Store / Google Play",
            2,
            3,
            "Mobilni tim",
            "Predati verziju ranije, pratiti smernice prodavnica.",
        ),
        R(
            RISK,
            "Nedovoljan kapacitet razvoja zbog drugih projekata",
            3,
            3,
            "IT razvoj",
            "Rezervisati tim na početku; prioriteti potvrđeni od uprave.",
        ),
        R(
            ASSUMPTION,
            "Procesor/partner podržava potrebne funkcije bez izmena",
            2,
            3,
            "Product",
            "Potvrditi kroz tehničku analizu u fazi dizajna.",
        ),
    ],
    stakeholders=[
        S("Uprava", "Interno", "Sponzor", "A", 3, 2),
        S("Product menadžer", "Interno", "Vlasnik proizvoda", "R", 3, 3),
        S("IT razvoj (backend i mobilni)", "Interno", "Razvoj", "R", 2, 3),
        S("QA", "Interno", "Testiranje", "R", 1, 2),
        S("Compliance", "Interno", "Usklađenost servisa", "C", 3, 2),
        S("Bezbednost informacija", "Interno", "DPIA i penetracioni test", "C", 2, 2),
        S("Marketing", "Interno", "Lansiranje", "C", 1, 2),
        S("Korisnička podrška", "Interno", "Podrška korisnicima", "I", 1, 3),
    ],
    documents=[
        D("Poslovni slučaj i KPI", "Prezentacija", "Product"),
        D("Poslovni zahtevi (BRD)", "Poslovni zahtevi (BRD)", "Product"),
        D("Specifikacija proizvoda (PRD)", "Specifikacija proizvoda (PRD)", "Product"),
        D("Compliance analiza servisa", "Compliance analiza", "Compliance"),
        D("DPIA", "Procena uticaja na zaštitu podataka (DPIA)", "Bezbednost informacija"),
        D("Tehnička arhitektura", "Tehnička specifikacija", "IT razvoj"),
        D("Test plan", "Test plan", "QA"),
        D("Plan lansiranja", "Plan puštanja u rad", "Product"),
    ],
)

# --- Integracija sa partnerom (API) --------------------------------------------------------------

INTEGRATION = build(
    [
        (
            "Analiza",
            [
                T("Pregled API dokumentacije partnera", 3, 8, "IT razvoj", "Analiza", "high"),
                T(
                    "Mapiranje podataka i tokova (slanje, status, povraćaj)",
                    4,
                    12,
                    "Product",
                    "Specifikacija",
                    "high",
                ),
                T("Tehnička specifikacija integracije", 4, 12, "IT razvoj", "Specifikacija"),
            ],
        ),
        (
            "Priprema",
            [
                [
                    T(
                        "Pristup test okruženju, ključevi i sertifikati",
                        3,
                        4,
                        "DevOps i infrastruktura",
                        "Infrastruktura",
                        "high",
                        ("partner",),
                    ),
                    T(
                        "Bezbednosni zahtevi (šifrovanje, IP liste, VPN)",
                        3,
                        6,
                        "Bezbednost informacija",
                        "Bezbednost",
                    ),
                ],
            ],
        ),
        (
            "Razvoj",
            [
                T("Razvoj adaptera i poslovne logike", 10, 60, "Backend", "Razvoj", "high"),
                [
                    T(
                        "Obrada grešaka, ponovni pokušaji i usaglašavanje",
                        4,
                        16,
                        "Backend",
                        "Razvoj",
                    ),
                    T(
                        "Monitoring i alarmi za integraciju",
                        2,
                        6,
                        "DevOps i infrastruktura",
                        "Infrastruktura",
                    ),
                ],
            ],
        ),
        (
            "Testiranje",
            [
                T("Testiranje u test okruženju partnera", 5, 20, "QA", "Testiranje i QA", "high"),
                T(
                    "Sertifikacija kod partnera",
                    4,
                    6,
                    "IT razvoj",
                    "Testiranje i QA",
                    "high",
                    ("partner",),
                ),
            ],
        ),
        (
            "Puštanje u rad",
            [
                T(
                    "Prelazak na produkcione ključeve i konfiguraciju",
                    1,
                    3,
                    "DevOps i infrastruktura",
                    "Puštanje u rad",
                    "high",
                ),
                T("Probne produkcione transakcije", 2, 4, "Operacije", "Puštanje u rad"),
                T("Praćenje prvih nedelju dana", 7, 6, "Operacije", "Podrška"),
            ],
        ),
    ],
    milestones=[
        ("Specifikacija gotova", "Tehnička specifikacija integracije"),
        ("Sertifikacija završena", "Sertifikacija kod partnera"),
        ("Integracija u produkciji", "Probne produkcione transakcije"),
    ],
    budget={"Interni rad": to_minor(900000), "Bezbednost i testiranje": to_minor(80000)},
    risks=[
        R(
            RISK,
            "Nepotpuna ili zastarela API dokumentacija partnera",
            3,
            3,
            "IT razvoj",
            "Rani tehnički sastanak; spisak pitanja i kontakt za podršku.",
        ),
        R(
            RISK,
            "Nestabilno test okruženje partnera",
            3,
            2,
            "QA",
            "Mock servis; dogovoreni termini testiranja.",
        ),
        R(
            DEPENDENCY,
            "Partner mora da odobri sertifikaciju",
            2,
            3,
            "IT razvoj",
            "Rezervisati termin sertifikacije unapred.",
        ),
    ],
    stakeholders=[
        S("Product menadžer", "Interno", "Vođa projekta", "A", 3, 3),
        S("Backend tim", "Interno", "Razvoj integracije", "R", 2, 3),
        S("DevOps", "Interno", "Okruženja i pristupi", "R", 1, 2),
        S("Tehnički kontakt partnera", "Partner", "API i sertifikacija", "C", 2, 3),
        S("Operacije", "Interno", "Praćenje posle puštanja", "I", 1, 2),
    ],
    documents=[
        D("API dokumentacija partnera", "API dokumentacija", "IT razvoj", DocStatus.APPROVED),
        D("Tehnička specifikacija integracije", "Tehnička specifikacija", "IT razvoj"),
        D("Izveštaj o sertifikaciji", "Test izveštaj / UAT zapisnik", "QA"),
    ],
)

# --- Regulatorni zahtev --------------------------------------------------------------------------

REGULATORY = build(
    [
        (
            "Analiza propisa",
            [
                T(
                    "Analiza novog propisa ili odluke regulatora",
                    4,
                    10,
                    "Compliance",
                    "Usklađenost (compliance)",
                    "high",
                ),
                T("Gap analiza: šta danas ne ispunjavamo", 5, 16, "Compliance", "Analiza", "high"),
                T("Procena uticaja na procese, sisteme i korisnike", 3, 8, "Product", "Analiza"),
            ],
        ),
        (
            "Plan usklađivanja",
            [
                T("Plan aktivnosti sa rokovima i nosiocima", 2, 6, "Product", "Analiza", "high"),
                T("Odobrenje plana od uprave", 1, 2, "Uprava", "Odobrenje", "urgent"),
            ],
        ),
        (
            "Sprovođenje",
            [
                [
                    T(
                        "Izmene internih akata i procedura",
                        7,
                        20,
                        "Compliance",
                        "Dokumentacija",
                        "high",
                    ),
                    T("Izmene sistema i aplikacije", 12, 60, "IT razvoj", "Razvoj", "high"),
                    T("Izmene ugovora i opštih uslova", 6, 12, "Pravna služba", "Pravno i ugovori"),
                ],
                T("Testiranje izmena", 4, 16, "QA", "Testiranje i QA"),
                T("Obuka zaposlenih i mreže", 3, 12, "Compliance", "Obuka"),
            ],
        ),
        (
            "Potvrda usklađenosti",
            [
                T(
                    "Interna provera usklađenosti",
                    3,
                    8,
                    "Interna revizija",
                    "Usklađenost (compliance)",
                    "high",
                ),
                T(
                    "Izveštaj ili obaveštenje regulatoru",
                    2,
                    4,
                    "Compliance",
                    "Izveštavanje",
                    "urgent",
                ),
            ],
        ),
    ],
    milestones=[
        ("Plan odobren", "Odobrenje plana od uprave"),
        ("Usklađenost potvrđena", "Izveštaj ili obaveštenje regulatoru"),
    ],
    budget={"Interni rad": to_minor(600000), "Pravne usluge": to_minor(100000)},
    risks=[
        R(
            RISK,
            "Rok regulatora je kraći od potrebnog vremena za IT izmene",
            3,
            4,
            "Product",
            "Rano pokretanje IT izmena; privremena manuelna kontrola.",
        ),
        R(
            RISK,
            "Različito tumačenje propisa",
            2,
            3,
            "Compliance",
            "Konsultacija sa pravnim savetnikom ili udruženjem.",
        ),
        R(
            ISSUE,
            "Nedostaju podaci za izveštavanje u traženom formatu",
            2,
            3,
            "Analitika i podaci",
            "Proveriti izvore podataka u gap analizi.",
        ),
    ],
    stakeholders=[
        S("Compliance", "Interno", "Nosilac usklađenosti", "A", 3, 3),
        S("Product menadžer", "Interno", "Koordinacija", "R", 2, 3),
        S("IT razvoj", "Interno", "Izmene sistema", "R", 2, 2),
        S("Pravna služba", "Interno", "Akti i ugovori", "C", 2, 2),
        S("Interna revizija", "Interno", "Nezavisna provera", "C", 2, 1),
        S("Narodna banka Srbije", "Regulator", "Regulator", "I", 3, 2),
    ],
    documents=[
        D("Tekst propisa", "Ostalo", "Compliance", DocStatus.APPROVED),
        D("Gap analiza", "Compliance analiza", "Compliance"),
        D("Plan usklađivanja", "Izveštaj", "Product"),
        D("Izmenjene interne procedure", "Interna procedura", "Compliance"),
    ],
)

# --- Istraživanje i discovery --------------------------------------------------------------------

RESEARCH = build(
    [
        (
            "Priprema",
            [
                T("Istraživačka pitanja i hipoteze", 2, 4, "Product", "Istraživanje", "high"),
                T("Plan istraživanja i izbor ispitanika", 2, 4, "Product", "Istraživanje"),
            ],
        ),
        (
            "Prikupljanje",
            [
                [
                    T(
                        "Intervjui sa korisnicima (8 do 12)",
                        8,
                        20,
                        "Product",
                        "Istraživanje",
                        "high",
                    ),
                    T("Anketa", 7, 6, "Marketing", "Istraživanje"),
                    T(
                        "Analiza podataka iz aplikacije i podrške",
                        5,
                        12,
                        "Product",
                        "Analitika i podaci",
                    ),
                ],
            ],
        ),
        (
            "Sinteza",
            [
                T("Sinteza nalaza i persone", 4, 12, "Product", "Analiza", "high"),
                T("Preporuke i prioriteti", 2, 6, "Product", "Analiza", "high"),
                T("Prezentacija nalaza", 1, 3, "Product", "Komunikacija"),
            ],
        ),
    ],
    milestones=[("Nalazi predstavljeni", "Prezentacija nalaza")],
    budget={"Interni rad": to_minor(250000), "Ostalo": to_minor(30000)},
    risks=[
        R(
            RISK,
            "Nedovoljan broj ispitanika",
            3,
            2,
            "Product",
            "Regrutovati preko podrške i aplikacije; mala nagrada za učešće.",
        ),
    ],
    stakeholders=[
        S("Product menadžer", "Interno", "Vodi istraživanje", "A", 3, 3),
        S("Korisnička podrška", "Interno", "Uvid u žalbe i pitanja", "C", 1, 2),
        S("Uprava", "Interno", "Prima preporuke", "I", 3, 2),
    ],
    documents=[
        D("Plan istraživanja", "Ostalo", "Product"),
        D("Izveštaj sa nalazima", "Izveštaj", "Product"),
    ],
)

# --- Analitika i izveštavanje --------------------------------------------------------------------

ANALYTICS = build(
    [
        (
            "Zahtevi",
            [
                T(
                    "Pitanja na koja izveštaj odgovara i ključne metrike",
                    2,
                    4,
                    "Product",
                    "Poslovni zahtevi",
                    "high",
                ),
                T("Izvori podataka i pristupi", 3, 6, "IT razvoj", "Analitika i podaci"),
            ],
        ),
        (
            "Izrada",
            [
                T("Provera kvaliteta podataka", 3, 8, "Product", "Analitika i podaci", "high"),
                T("Model podataka i obračuni", 4, 16, "IT razvoj", "Analitika i podaci"),
                T("Dashboard i vizuelizacija", 4, 16, "Product", "Analitika i podaci"),
            ],
        ),
        (
            "Validacija i uvođenje",
            [
                T(
                    "Provera brojeva sa finansijama i operacijama",
                    2,
                    6,
                    "Finansije",
                    "Testiranje i QA",
                    "high",
                ),
                T("Automatsko osvežavanje i pristupi", 2, 6, "IT razvoj", "Infrastruktura"),
                T("Kratka obuka korisnika izveštaja", 1, 3, "Product", "Obuka"),
            ],
        ),
    ],
    milestones=[("Izveštaj u upotrebi", "Kratka obuka korisnika izveštaja")],
    budget={"Interni rad": to_minor(300000), "Softver i licence": to_minor(40000)},
    risks=[
        R(
            ISSUE,
            "Podaci iz različitih sistema se ne slažu",
            3,
            3,
            "Product",
            "Definisati jedan izvor istine i pravila usaglašavanja.",
        ),
    ],
    stakeholders=[
        S("Product menadžer", "Interno", "Vlasnik izveštaja", "A", 2, 3),
        S("Finansije", "Interno", "Validacija brojeva", "C", 2, 2),
        S("Uprava", "Interno", "Korisnik izveštaja", "I", 3, 3),
    ],
    documents=[D("Definicije metrika", "Specifikacija proizvoda (PRD)", "Product")],
)

# --- Promo kampanja sa partnerom -----------------------------------------------------------------

CAMPAIGN = build(
    [
        (
            "Priprema",
            [
                T("Cilj, mehanika i ciljna grupa kampanje", 3, 6, "Product", "Marketing", "high"),
                [
                    T(
                        "Budžet i nagradni fond (sa partnerom)",
                        3,
                        4,
                        "Finansije",
                        "Finansije",
                        "high",
                        ("partner",),
                    ),
                    T(
                        "Pravila nagradne igre ili promocije",
                        4,
                        8,
                        "Pravna služba",
                        "Pravno i ugovori",
                        "high",
                    ),
                ],
                T(
                    "Pravna i compliance provera",
                    3,
                    4,
                    "Compliance",
                    "Usklađenost (compliance)",
                    "high",
                ),
            ],
        ),
        (
            "Izrada",
            [
                [
                    T("Kreativa i poruke (sa partnerom)", 6, 16, "Marketing", "Marketing"),
                    T(
                        "Tehnička podrška: promo kod, praćenje, izveštaj",
                        6,
                        20,
                        "IT razvoj",
                        "Razvoj",
                    ),
                ],
                T("Obuka mreže i korisničke podrške", 2, 6, "Prodaja", "Obuka"),
            ],
        ),
        (
            "Sprovođenje",
            [
                T("Trajanje kampanje i nedeljno praćenje", 30, 16, "Product", "Marketing", "high"),
                T("Izbor dobitnika i dodela nagrada", 3, 6, "Marketing", "Marketing"),
                T("Izveštaj o rezultatima za upravu i partnera", 2, 6, "Product", "Izveštavanje"),
            ],
        ),
    ],
    milestones=[
        ("Start kampanje", "Obuka mreže i korisničke podrške"),
        ("Kraj kampanje", "Trajanje kampanje i nedeljno praćenje"),
    ],
    budget={"Marketing": to_minor(800000), "Interni rad": to_minor(200000)},
    risks=[
        R(
            RISK,
            "Kašnjenje odobrenja partnera za kreativu",
            3,
            2,
            "Marketing",
            "Dogovoriti rokove odobrenja unapred.",
        ),
        R(
            RISK,
            "Zloupotreba promo koda",
            2,
            3,
            "IT razvoj",
            "Ograničenja po korisniku i praćenje neobičnih obrazaca.",
        ),
    ],
    stakeholders=[
        S("Product menadžer", "Interno", "Vođa kampanje", "A", 2, 3),
        S("Marketing", "Interno", "Kreativa i mediji", "R", 2, 3),
        S("Partner", "Partner", "Saradnja i nagradni fond", "C", 3, 3),
        S("Pravna služba", "Interno", "Pravila", "C", 2, 1),
        S("Prodajna mreža", "Interno", "Sprovođenje na terenu", "I", 1, 2),
    ],
    documents=[
        D("Pravila nagradne igre", "Interna procedura", "Pravna služba"),
        D("Plan kampanje", "Prezentacija", "Marketing"),
        D("Izveštaj o rezultatima", "Izveštaj", "Product"),
    ],
)

# --- Opšti projekat ------------------------------------------------------------------------------

GENERAL = build(
    [
        (
            "Inicijacija",
            [
                T("Cilj, obim i kriterijumi uspeha", 2, 4, "Product", "Poslovni zahtevi", "high"),
                T("Kick-off sa učesnicima", 1, 2, "Product", "Sastanak"),
            ],
        ),
        ("Planiranje", [T("Plan rada, rokovi i budžet", 3, 6, "Product", "Analiza", "high")]),
        ("Realizacija", [T("Realizacija (razdeli na zadatke)", 20, None, "", "")]),
        ("Zatvaranje", [T("Primopredaja i izveštaj", 2, 4, "Product", "Izveštavanje")]),
    ],
    milestones=[("Završetak projekta", "Primopredaja i izveštaj")],
    budget={},
    stakeholders=[S("Sponzor projekta", "Interno", "Odobrava i prima rezultat", "A", 3, 2)],
)

BUILTIN: dict[str, dict] = {
    "onboarding": {
        "name": "Onboarding partnera",
        "description": "Due diligence i AML, ugovaranje, integracija, operativna priprema, "
        "pilot i go-live, sa tipičnim rizicima i dokumentima.",
        "data": ONBOARDING,
    },
    "novi_servis": {
        "name": "Novi servis u aplikaciji (TNapp)",
        "description": "Discovery, BRD i PRD, compliance i DPIA, dizajn, razvoj, testiranje, "
        "objava u prodavnicama, lansiranje i praćenje KPI.",
        "data": NEW_SERVICE,
    },
    "integracija": {
        "name": "Integracija sa partnerom (API)",
        "description": "Analiza API-ja, specifikacija, razvoj, sertifikacija i prelazak "
        "u produkciju.",
        "data": INTEGRATION,
    },
    "regulativa": {
        "name": "Regulatorni zahtev",
        "description": "Analiza propisa, gap analiza, izmene procedura i sistema, obuka i "
        "izveštaj regulatoru.",
        "data": REGULATORY,
    },
    "istrazivanje": {
        "name": "Istraživanje i discovery",
        "description": "Pitanja i hipoteze, intervjui, anketa i podaci, sinteza i preporuke.",
        "data": RESEARCH,
    },
    "analitika": {
        "name": "Analitika i izveštaj",
        "description": "Metrike, izvori i kvalitet podataka, dashboard, validacija i uvođenje.",
        "data": ANALYTICS,
    },
    "kampanja": {
        "name": "Promo kampanja sa partnerom",
        "description": "Mehanika i pravila, compliance, kreativa, promo kod, sprovođenje i "
        "izveštaj.",
        "data": CAMPAIGN,
    },
    "opsti": {
        "name": "Opšti projekat",
        "description": "Kostur u četiri faze za bilo koji projekat.",
        "data": GENERAL,
    },
}
