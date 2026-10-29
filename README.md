# Etapa

Desktop aplikacija za upravljanje projektima, rokovima i budžetom — Gant, Kanban, lista zadataka,
praćenje troškova i deljenje stanja projekta linkom. Radi lokalno, bez naloga i servera.

## Pokretanje na Windows-u (prvi put)

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

## Demo podaci

U VS Code → Run and Debug izaberi **Demo podaci: napuni .data bazu**, pa
**Etapa: pokreni sa demo bazom**. Demo baza je u folderu `.data/` i ne dira tvoje prave podatke.

## Gde su podaci

`%APPDATA%\Etapa\etapa.db` — automatske kopije u `%APPDATA%\Etapa\backups\` (poslednjih 10).

## Testovi

```powershell
pytest
ruff check .
```
