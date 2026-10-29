"""Putanje do podataka aplikacije.

Na Windows-u podaci su u %APPDATA%/Etapa, na ostalim sistemima u ~/.local/share/Etapa.
Promenljiva okruženja ETAPA_DATA_DIR menja folder (koristi se za demo bazu i testove).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app import APP_NAME

DB_FILENAME = "etapa.db"
BACKUP_KEEP = 10


def default_data_dir() -> Path:
    override = os.environ.get("ETAPA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


@dataclass(frozen=True)
class Paths:
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def receipts_dir(self) -> Path:
        return self.data_dir / "receipts"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path.as_posix()}"

    def ensure(self) -> Paths:
        for folder in (self.data_dir, self.backups_dir, self.receipts_dir):
            folder.mkdir(parents=True, exist_ok=True)
        return self


def get_paths(data_dir: Path | None = None) -> Paths:
    return Paths(data_dir or default_data_dir())
