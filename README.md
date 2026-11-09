# Etapa

Desktop aplikacija za upravljanje projektima, rokovima i budžetom: **Lista**, **Kanban**,
**Gant** sa zavisnostima i milestone-ima, **Budžet** sa troškovima i prihodima, i **deljenje
linkom** (pregled + komentari klijenta). Radi lokalno, bez naloga i bez servera; svi podaci su
u jednom fajlu na tvom računaru.

## Šta ima

- **Pregled svih projekata** (Ctrl+0): napredak, budžet, otvoreni rizici, kašnjenja i blokirani
  zadaci, rokovi u narednih 14 dana, sati po danima ove nedelje
- **Lista, Kanban i Gant** po projektu: podzadaci, zavisnosti mišem, milestone-i, pomeranje
  zavisnih zadataka, istorija izmena
- **Zadaci** sa nosiocem, fazom i vrstom rada; statusi Za uraditi, U toku, Na pregledu, Blokirano,
  Na čekanju, Završeno
- **Registar projekta** (Ctrl+5): rizici i problemi (verovatnoća × uticaj), zainteresovane strane
  (RACI, uticaj, interes), dokumenta i linkovi, log odluka
- **Budžet**: troškovi i prihodi u 8 valuta po kursu, 13 kategorija (i nove iz dijaloga),
  upozorenja, grafikon
- **Merenje vremena**: tajmer na zadatku (prikazan u statusnoj traci) ili ručni unos sati
- **Šabloni projekata** po fazama, sa zavisnostima, milestone-ima, budžetom, rizicima, ljudima i
  dokumentima: onboarding partnera, novi servis u TNapp, integracija sa partnerom, regulatorna
  usklađenost, istraživanje korisnika, analitika i izveštavanje, kampanja, opšti; i tvoji
- Padajuće liste sa predlozima uz **proizvoljan unos** (vrsta projekta, faza, nosilac, organizacija)
- **Podsetnici** za rokove koji ističu ili kasne (obaveštenje u sistemskoj traci)
- **Izvoz**: PDF izveštaj sa Gantom, rizicima i odlukama (Ctrl+P), Excel sa svim podacima i
  registrom, CSV
- **Deljenje linkom u lokalnoj mreži** sa PIN-om i komentarima gledalaca (opciono preko interneta)
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

Najlakše: gotov instaler je na stranici
[Releases](https://github.com/gru-webdesign/product_management/releases). Pravi ga GitHub
(Actions → „Windows instaler“) za svaki tag `v*`, a može i ručno dugmetom *Run workflow*.
Aplikacija kreće prazna, bez demo podataka; podaci su u `%APPDATA%\Etapa`.

Lokalno, na Windows-u:

Jednom instaliraj [Inno Setup 6](https://jrsoftware.org/isdl.php), pa:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

Skripta pokrene testove, spakuje aplikaciju (PyInstaller → `dist\Etapa\Etapa.exe`), proveri da
se `.exe` pokreće, i napravi instaler `installer\Output\Etapa-Setup-1.2.2.exe`. Instaler ne
traži administratorska prava; deinstalacija ne briše podatke.

## Deljenje linkom

Podrazumevano deljenje radi **u lokalnoj mreži**, bez interneta i bez spoljnog servera. Dugme
**Podeli** → **Uključi link** daje adresu tipa `http://192.168.1.20:8765/p/...`, koju otvaraju
računari i telefoni u istoj mreži. Stranica je uvek ažurna, komentari stižu odmah u aplikaciju,
a link radi dok je Etapa otvorena. Prvi put Windows može da pita za dozvolu u zaštitnom zidu:
dozvoli za privatnu mrežu. Port se menja u **Podešavanja → Deljenje**.

Za deljenje preko interneta, u istom podešavanju izaberi **Internet, preko Cloudflare Worker-a**
i postavi Worker po uputstvu [share_worker/README.md](share_worker/README.md).

## Gde su podaci

`%APPDATA%\Etapa\etapa.db`, a automatske kopije u `%APPDATA%\Etapa\backups\` (poslednjih 10,
pravi se pri svakom pokretanju). **Datoteka → Vrati bazu iz kopije…** vraća stariju verziju.

## Razvoj

```powershell
pytest                                   # 122 testa (servisi + UI, bez prozora)
ruff check . ; ruff format .             # stil koda
python scripts\screenshots.py shots      # snimci svih ekrana sa demo podacima
cd share_worker ; npm test               # testovi Worker-a
```

Struktura, pravila koda i stanje po koracima: [CLAUDE.md](CLAUDE.md).

## Nova verzija

**Pomoć → Proveri novu verziju…** proverava poslednje izdanje na GitHub-u. Da bi ovo radilo,
gotov instaler objavi kao *Release* sa oznakom verzije (npr. `v1.1.0`).
