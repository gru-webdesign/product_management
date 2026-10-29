# Pravi Etapa instaler jednom komandom (Windows PowerShell, iz korena projekta):
#     powershell -ExecutionPolicy Bypass -File scripts\build.ps1
#
# Koraci: venv → zavisnosti → testovi → PyInstaller (dist\Etapa) → provera .exe-a →
#         Inno Setup (installer\Output\Etapa-Setup-<verzija>.exe)
# Opcije:  -SkipTests   preskoči testove
param([switch]$SkipTests)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

$version = (Select-String -Path "app\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Step "Etapa $version"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Step "Pravim virtuelno okruženje (.venv)"
    py -3 -m venv .venv
}
$py = Join-Path $root ".venv\Scripts\python.exe"

Step "Instaliram zavisnosti"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -e ".[dev]" pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Instalacija zavisnosti nije uspela." }

if (-not $SkipTests) {
    Step "Pokrećem testove"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Testovi nisu prošli — instaler se ne pravi." }
}

Step "Pakujem aplikaciju (PyInstaller)"
& $py -m PyInstaller --noconfirm --clean installer\etapa.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller nije uspeo." }

Step "Proveravam spakovani Etapa.exe"
$env:ETAPA_DATA_DIR = Join-Path $env:TEMP "etapa-smoke-test"
if (Test-Path $env:ETAPA_DATA_DIR) { Remove-Item -Recurse -Force $env:ETAPA_DATA_DIR }
$proc = Start-Process -FilePath "dist\Etapa\Etapa.exe" -ArgumentList "--smoke-test" -PassThru -Wait
Remove-Item Env:\ETAPA_DATA_DIR
if ($proc.ExitCode -ne 0) { throw "Etapa.exe se nije pokrenuo ispravno (kod $($proc.ExitCode))." }
Write-Host "Etapa.exe radi."

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Warning "Inno Setup 6 nije pronađen — preskačem instaler. Aplikacija je u dist\Etapa\."
    Write-Warning "Instaliraj ga sa https://jrsoftware.org/isdl.php pa ponovo pokreni skriptu."
    exit 0
}

Step "Pravim instaler (Inno Setup)"
& $iscc "/DAppVersion=$version" "installer\setup.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup nije uspeo." }

$out = Join-Path $root "installer\Output\Etapa-Setup-$version.exe"
Step "Gotovo: $out"
