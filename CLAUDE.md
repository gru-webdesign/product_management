# Etapa — kontekst projekta

Desktop aplikacija za **jednog korisnika** za vođenje projekata, rokova i budžeta. Radi potpuno
lokalno (SQLite), bez servera i naloga. Jedina veza sa internetom je opciono **deljenje linkom**:
snimak stanja projekta za pregled + komentari gledalaca, preko jednog Cloudflare Worker-a.

Pun plan: https://claude.ai/artifact/8yjLN6prd3wowrenHYMQbU
Repo: https://github.com/gru-webdesign/product_management

## Stack

- Python 3.12+, PySide6 (Qt 6) za UI, Qt Charts za grafikone budžeta
- SQLite + SQLAlchemy 2 (typed `Mapped[...]`), Alembic migracije (pokreću se same pri startu)
- Jinja2 za HTML snimak, httpx za Cloudflare API, keyring za API token
- Cloudflare Worker + KV (`share_worker/`, JavaScript) — servira snimak i čuva komentare
- PyInstaller + Inno Setup za Windows instaler
- pytest + pytest-qt, ruff (linija 100)

## Struktura

```
app/
  main.py            bootstrap(): backup → migracije → podrazumevani podaci → MainWindow
  config.py          putanje (%APPDATA%/Etapa; ETAPA_DATA_DIR menja folder)
  db/base.py         Base, IdMixin (UUID), TimestampMixin, Database, alembic_config
  db/models.py       sve tabele
  db/migrations/     Alembic (versions/ se ne lintuje)
  services/          poslovna logika BEZ Qt-a (testira se bez UI-ja)
  share/             snimak, render, Cloudflare klijent, keyring
  ui/                sve što je Qt; views/, dialogs/, widgets/, models/
share_worker/        Cloudflare Worker
scripts/seed_demo.py demo projekat (10 zadataka, 8 zavisnosti, budžet, troškovi)
tests/
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
- Svaka izmena zadatka/projekta upisuje red u `activity_log` (servis `activity.py`, Korak 4).
- Posle svakog koraka: `ruff check . && ruff format --check . && pytest`, pa commit i
  ažuriranje sekcije „Stanje“ ispod.

## Komande

```powershell
py -3.12 -m venv .venv
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
- [x] Korak 2 — baza: modeli svih tabela, migracija 0001, backup (10 kopija), podrazumevana
      podešavanja i kategorije budžeta, demo podaci, 13 testova
- [ ] Korak 3 — glavni prozor: sidebar projekata, tabovi Lista/Kanban/Gant/Budžet, dijalog projekta, teme
- [ ] Korak 4 — lista zadataka, dijalog zadatka, podzadaci, filteri, pretraga, istorija izmena
- [ ] Korak 5 — Kanban
- [ ] Korak 6 — Gant deo 1: osa, zum, trake, drag/resize, „danas“
- [ ] Korak 7 — test korisnika (Dan 1)
- [ ] Korak 8 — popravke sa Dana 1
- [ ] Korak 9 — Gant deo 2: zavisnosti, zabrana ciklusa, pomeranje zavisnih, milestone
- [ ] Korak 10 — budžet i troškovi
- [ ] Korak 11 — Cloudflare Worker
- [ ] Korak 12 — deljenje u app-u
- [ ] Korak 13 — doterivanje (CSV, podešavanja, prečice, prazni ekrani, ikonica)
- [ ] Korak 14 — instaler
- [ ] Korak 15 — završni test, v1.0

Van v1.0 (ide u v1.1): tajmer, prilozi/slike računa, Excel/PDF, dashboard, engleski, šabloni,
notifikacije.
