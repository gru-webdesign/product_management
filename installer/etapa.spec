# PyInstaller recept za Etapa.  Pokretanje iz korena projekta:
#     pyinstaller --noconfirm --clean installer/etapa.spec
# Rezultat: dist/Etapa/Etapa.exe (folder, brže pokretanje nego jedan fajl).
# ruff: noqa
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821  (SPECPATH daje PyInstaller)
APP = ROOT / "app"

datas = [
    (str(APP / "resources"), "app/resources"),
    (str(APP / "share" / "templates"), "app/share/templates"),
    # Alembic učitava env.py i migracije kao fajlove, pa moraju biti pravi .py fajlovi
    (str(APP / "db" / "migrations"), "app/db/migrations"),
]

hiddenimports = (
    collect_submodules("alembic")
    + collect_submodules("keyring.backends")
    + ["sqlalchemy.dialects.sqlite", "app.db.models"]
)
if sys.platform == "win32":
    hiddenimports += ["win32ctypes.core"]

excludes = [
    "tkinter",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtPdf",
    "PySide6.QtDesigner",
    "pytest",
    "pytestqt",
    "numpy",
    "PIL",
    "matplotlib",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "installer" / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Etapa",
    console=False,
    icon=str(ROOT / "installer" / "icon.ico") if sys.platform == "win32" else None,
    version=str(ROOT / "installer" / "version_info.txt") if sys.platform == "win32" else None,
    upx=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="Etapa",
    upx=False,
)
