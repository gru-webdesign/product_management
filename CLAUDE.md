# Etapa — kontekst projekta

Desktop aplikacija za **jednog korisnika** za vođenje projekata, rokova i budžeta. Radi potpuno
lokalno (SQLite), bez servera i naloga. Jedina veza sa internetom je opciono **deljenje linkom**:
snimak stanja projekta za pregled + komentari gledalaca, preko jednog Cloudflare Worker-a.

Pun plan: https://claude.ai/artifact/8yjLN6prd3wowrenHYMQbU
Repo: https://github.com/gru-webdesign/product_management

## Stack

- Python 3.12+, PySide6 (Qt 6) za UI, Qt Charts za grafikone budžeta
- SQLite + SQLAlchemy 2 (typed `Mapped[...]`), Alembic migracije (pokreću se same pri startu)
- Jinja2 za HTML snimak, httpx za Worker API, keyring za tajni ključ Worker-a
- Cloudflare Worker + KV (`share_worker/`, JavaScript) — servira snimak i čuva komentare
- PyInstaller + Inno Setup za Windows instaler
- pytest + pytest-qt, ruff (linija 100)

## Struktura

```
app/
  main.py              bootstrap(): backup → migracije → podrazumevani podaci → MainWindow
                       (--smoke-test: otvori prozor i zatvori, za proveru .exe-a)
  config.py            putanje (%APPDATA%/Etapa; ETAPA_DATA_DIR menja folder)
  labels.py            srpski nazivi i boje statusa/prioriteta
  db/base.py           Base, IdMixin (UUID), TimestampMixin, Database, alembic_config
  db/models.py         sve tabele
  db/migrations/       Alembic (versions/ se ne lintuje)
  services/            poslovna logika BEZ Qt-a: projects, tasks, dependencies, milestones,
                       gantt_math, budget, sharing, activity, backup, defaults, money, export_csv,
                       export_xlsx, timetracking, dashboard, templates, reminders, updates
  share/               snapshot (šta se deli), render + templates/share.html, client (Worker),
                       secrets (keyring)
  ui/
    main_window.py     sidebar + zaglavlje + tabovi, meniji, deljenje u pozadini
    context.py         AppContext: izabrani projekat, pretraga, data_changed, run()
    theme.py, icons.py tokeni boja (svetla/tamna), QSS, Geist fontovi, Phosphor ikonice
                       (resources/icons/phosphor, boja se menja u kodu)
    export.py          dijalozi za izvoz (CSV, Excel, PDF); report.py pravi PDF (QTextDocument)
    reminders.py       podsetnici za rokove (sistemska traka, provera na 30 min)
    background.py      mrežni poslovi u QThreadPool-u (sopstvena sesija po poslu)
    views/             dashboard_view, list_view, kanban_view, budget_view,
                       gantt/ (chart, items, model; load_chart_data koristi i PDF)
    dialogs/           project (sa šablonom), task (6 tabova, i Vreme), milestone, cost,
                       budget, share, settings, restore, templates
    widgets/           card (kartica sa senkom), kpi (brojka + ikonica), fields, paint
                       (bedževi, trake), comments_panel, timer_widget (tajmer u statusnoj traci)
share_worker/          Cloudflare Worker (src/index.js) + Node testovi + README za postavljanje
installer/             etapa.spec (PyInstaller), setup.iss (Inno Setup), icon.ico, launch.py
scripts/               seed_demo.py, screenshots.py, build.ps1
tests/                 115 testova (servisi + UI preko pytest-qt, bez prozora)
```

## Pravila koda

- Kod, imena i komentari u kodu: engleski identifikatori, komentari i UI tekst na **srpskom (latinica)**.
- Novac je uvek `int` u najmanjoj jedinici (`*_minor`, 1 RSD = 100 para) — nikad float.
  Pomoćne funkcije: `app/services/money.py` (`to_minor`, `to_base_minor`, `format_money`).
  Trošak/prihod čuva i `amount_base_minor` u osnovnoj valuti po kursu na dan unosa.
- Ključevi su UUID stringovi (`IdMixin`). Datumi zadataka su `date`, vremena `datetime` u UTC.
- Polje koje se zove `date` → anotacija `Mapped[dt.date]` (`import datetime as dt`), da ne zasenči tip.
- UI ne piše SQL direktno: ide kroz `app/services/*`. Servisi ne importuju Qt.
- Svaka izmena šeme = nova Alembic migracija:
  `alembic revision --autogenerate -m "opis"` pa proveri fajl; test `test_migrations_match_models`
  pada ako migracija nedostaje.
- Svaka izmena zadatka/projekta upisuje red u `activity_log` (`activity.apply_changes`).
- Promena datuma zadatka ide kroz `tasks.update`/`tasks.set_dates`, koji pozivaju
  `dependencies.propagate` (zavisni zadaci se pomeraju unapred, nikad unazad).
- Akcija iz događaja miša koja osvežava prikaz (Gant, Kanban, dvoklik u Listi) mora da se izvrši
  POSLE događaja: `QueuedConnection` ili `QTimer.singleShot(0, ...)`. Inače osvežavanje briše
  stavku koja još obrađuje događaj → pad aplikacije.
- Mreža (Worker) nikad u glavnoj niti za automatske poslove: `ui/background.run(db, fn, ...)`.
- U testovima tema se primenjuje jednom po sesiji (conftest), ne u svakom testu (sporo).
- Signal teme (`theme.manager().changed`) vezuj za metodu objekta, ne za lambda: lambda nadživi
  obrisan widget → RuntimeError.
- Dizajn: teget i belo. Tamna tema (podrazumevana) je cela teget (`#0A1128`), svetla ima belu
  površinu i teget sidebar. Dugme `primary` je belo/teget (token `primary`), plava (`accent`)
  je za podatke i izbor. Površine su `widgets/card.py` (Card, paint_card: senka bez
  QGraphicsEffect-a), brojke `widgets/kpi.py` (KpiCard, IconChip). Geist, Geist Mono samo za
  brojeve u kolonama; Phosphor ikonice; bez crta (— –) u vidljivom tekstu, bez VELIKIH naslova;
  radijusi: kontrole 8, kartice 12, ugnežđeno 10, pilule pune. Novi prikaz = sadržaj u Card,
  traka iznad sa marginom 8 levo/desno (poravnanje sa karticom).
- Posle svakog koraka: `ruff check . && ruff format --check . && pytest`, pa commit i
  ažuriranje sekcije „Stanje“ ispod.

## Komande

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m app.main                                     # prava baza
$env:ETAPA_DATA_DIR=".data"; python scripts/seed_demo.py   # demo baza
$env:ETAPA_DATA_DIR=".data"; python -m app.main
pytest
ruff check . ; ruff format .
```

## Stanje

- [x] Korak 1 — postavka: pyproject, .vscode (F5), .gitignore, prazan glavni prozor
- [x] Korak 2 — baza: modeli svih tabela, migracija 0001, backup (10 kopija), podrazumevani podaci
- [x] Korak 3 — glavni prozor: sidebar projekata, tabovi, dijalog projekta, svetla/tamna tema
- [x] Korak 4 — lista zadataka, dijalog zadatka, podzadaci, filteri, pretraga, istorija izmena
- [x] Korak 5 — Kanban sa prevlačenjem
- [x] Koraci 6 i 9 — Gant: osa, zum, drag/resize, zavisnosti mišem, pomeranje zavisnih, milestone
- [x] Korak 10 — budžet i troškovi (RSD/EUR/USD, kurs, upozorenja, grafikon, prihodi)
- [x] Koraci 11 i 12 — Cloudflare Worker + deljenje u aplikaciji, PIN, komentari
- [x] Korak 13 — doterivanje: CSV, podešavanja, prečice (F1), ikonica, pamćenje prozora
- [x] Korak 14 — instaler: PyInstaller spec, Inno Setup, scripts/build.ps1 (provereno pakovanje)
- [ ] Korak 7/15 — test korisnika na Windows-u, popravke, v1.0

v1.1 (verzija 1.1.0):
- [x] Redizajn: kobalt, Geist, Phosphor ikonice, nova ikonica aplikacije, zaglavlje projekta
- [x] Merenje vremena: tajmer (statusna traka), ručni unos, `actual_hours` = zbir unosa
- [x] Pregled svih projekata (Ctrl+0)
- [x] Šabloni projekata (3 ugrađena + sopstveni), migracija 0002
- [x] Podsetnici za rokove (sistemska traka)
- [x] Izvoz: PDF izveštaj sa Gantom (Ctrl+P), Excel (Ctrl+Shift+X), CSV (Ctrl+E)
- [x] Provera nove verzije (Pomoć, GitHub releases; treba objaviti Release `v1.1.0`)
- [x] Redizajn 2: teget/bela tema (tamna podrazumevana), kartice sa senkom, novi Pregled
  (prsten stanja, rokovi, poslednje izmene, sati po danima), sidebar sa napretkom projekata,
  Kanban kolone, prekidač teme dole levo

Šta korisnik treba sam da uradi (traži njegov nalog/računar):
- `scripts\build.ps1` na Windows-u (treba Inno Setup 6) → instaler
- postavljanje Worker-a na Cloudflare po `share_worker/README.md`

Odloženo (nije u v1.1): prilozi/slike računa, engleski jezik.
