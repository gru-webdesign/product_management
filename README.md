# Etapa

Desktop aplikacija za upravljanje projektima, rokovima i budžetom: **Lista**, **Kanban**,
**Gant** sa zavisnostima i milestone-ima, **Budžet** sa troškovima i prihodima, i **deljenje
linkom** (pregled + komentari klijenta). Radi lokalno, bez naloga i bez servera; svi podaci su
u jednom fajlu na tvom računaru.

## Pokretanje iz koda (Windows)

Potrebno: [Python 3.12+](https://www.python.org/downloads/) (pri instalaciji označi
**Add python.exe to PATH**), Git i VS Code.

```powershell
git clone https://github.com/gru-webdesign/product_management.git
cd product_management
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m app.main
```

Ako PowerShell javi da je pokretanje skripti zabranjeno, jednom pokreni:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

U VS Code: otvori folder, prihvati preporučene ekstenzije, izaberi interpreter `.venv`
(Ctrl+Shift+P → *Python: Select Interpreter*) i pokreni sa **F5**.

### Demo podaci

Run and Debug → **Demo podaci: napuni .data bazu**, pa **Etapa: pokreni sa demo bazom**.
Demo baza je u folderu `.data/` i ne dira tvoje prave podatke.

## Instaler (Etapa-Setup.exe)

Jednom instaliraj [Inno Setup 6](https://jrsoftware.org/isdl.php), pa:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Skripta pokrene testove, spakuje aplikaciju (PyInstaller → `dist\Etapa\Etapa.exe`), proveri da
se `.exe` pokreće, i napravi instaler `installer\Output\Etapa-Setup-0.1.0.exe`. Instaler ne
traži administratorska prava; deinstalacija ne briše podatke.

## Deljenje linkom

Jednom napravi besplatan Cloudflare Worker po uputstvu
[share_worker/README.md](share_worker/README.md), pa u aplikaciji
**Podešavanja → Deljenje** upiši njegovu adresu i tajni ključ. Posle toga dugme **Podeli** u
svakom projektu pravi link za pregled (opciono sa PIN-om), a komentari gledalaca stižu u
aplikaciju.

## Gde su podaci

`%APPDATA%\Etapa\etapa.db` — automatske kopije u `%APPDATA%\Etapa\backups\` (poslednjih 10,
pravi se pri svakom pokretanju). **Datoteka → Vrati bazu iz kopije…** vraća stariju verziju.

## Razvoj

```powershell
pytest                                   # 94 testa (servisi + UI, bez prozora)
ruff check . ; ruff format .             # stil koda
python scripts\screenshots.py shots      # snimci svih ekrana sa demo podacima
cd share_worker ; npm test               # testovi Worker-a
```

Struktura, pravila koda i stanje po koracima: [CLAUDE.md](CLAUDE.md).
