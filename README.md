# Etapa

Desktop aplikacija za upravljanje projektima, rokovima i budžetom: **Lista**, **Kanban**,
**Gant** sa zavisnostima i milestone-ima, **Budžet** sa troškovima i prihodima, i **deljenje
linkom** (pregled + komentari klijenta). Radi lokalno, bez naloga i bez servera; svi podaci su
u jednom fajlu na tvom računaru.

## Šta ima

- **Pregled svih projekata** (Ctrl+0): napredak, budžet, kašnjenja, rokovi u narednih 14 dana,
  sati po danima ove nedelje
- **Lista, Kanban i Gant** po projektu: podzadaci, zavisnosti mišem, milestone-i, pomeranje
  zavisnih zadataka, istorija izmena
- **Budžet**: troškovi i prihodi u RSD/EUR/USD po kursu, kategorije, upozorenja, grafikon
- **Merenje vremena**: tajmer na zadatku (prikazan u statusnoj traci) ili ručni unos sati
- **Šabloni projekata**: tri ugrađena (sajt, redizajn, kampanja) i tvoji, sačuvani iz
  postojećeg projekta
- **Podsetnici** za rokove koji ističu ili kasne (obaveštenje u sistemskoj traci)
- **Izvoz**: PDF izveštaj sa Gantom (Ctrl+P), Excel sa svim podacima, CSV
- **Deljenje linkom** sa PIN-om i komentarima gledalaca
- Svetla i tamna tema

## Pokretanje iz koda (Windows)

Potrebno: [Python 3.12 ili noviji](https://www.python.org/downloads/) (pri instalaciji označi
**Add python.exe to PATH**), Git i VS Code.

```powershell
git clone https://github.com/gru-webdesign/product_management.git
cd product_management
py -3 -m venv .venv
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
se `.exe` pokreće, i napravi instaler `installer\Output\Etapa-Setup-1.1.0.exe`. Instaler ne
traži administratorska prava; deinstalacija ne briše podatke.

## Deljenje linkom

Jednom napravi besplatan Cloudflare Worker po uputstvu
[share_worker/README.md](share_worker/README.md), pa u aplikaciji
**Podešavanja → Deljenje** upiši njegovu adresu i tajni ključ. Posle toga dugme **Podeli** u
svakom projektu pravi link za pregled (opciono sa PIN-om), a komentari gledalaca stižu u
aplikaciju.

## Gde su podaci

`%APPDATA%\Etapa\etapa.db`, a automatske kopije u `%APPDATA%\Etapa\backups\` (poslednjih 10,
pravi se pri svakom pokretanju). **Datoteka → Vrati bazu iz kopije…** vraća stariju verziju.

## Razvoj

```powershell
pytest                                   # 115 testova (servisi + UI, bez prozora)
ruff check . ; ruff format .             # stil koda
python scripts\screenshots.py shots      # snimci svih ekrana sa demo podacima
cd share_worker ; npm test               # testovi Worker-a
```

Struktura, pravila koda i stanje po koracima: [CLAUDE.md](CLAUDE.md).

## Nova verzija

**Pomoć → Proveri novu verziju…** proverava poslednje izdanje na GitHub-u. Da bi ovo radilo,
gotov instaler objavi kao *Release* sa oznakom verzije (npr. `v1.1.0`).
