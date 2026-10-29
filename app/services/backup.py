"""Automatske kopije baze.

Pri svakom pokretanju pravi se kopija preko SQLite backup API-ja (bezbedno i u WAL režimu),
a čuva se poslednjih BACKUP_KEEP kopija.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import BACKUP_KEEP, Paths

PREFIX = "etapa-"
SUFFIX = ".db"


def create_backup(
    paths: Paths, keep: int = BACKUP_KEEP, now: datetime | None = None
) -> Path | None:
    if not paths.db_path.exists():
        return None
    paths.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    target = paths.backups_dir / f"{PREFIX}{stamp}{SUFFIX}"
    n = 1
    while target.exists():  # dva starta u istoj sekundi
        target = paths.backups_dir / f"{PREFIX}{stamp}-{n}{SUFFIX}"
        n += 1

    src = sqlite3.connect(paths.db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    prune(paths, keep)
    return target


def list_backups(paths: Paths) -> list[Path]:
    if not paths.backups_dir.exists():
        return []
    return sorted(paths.backups_dir.glob(f"{PREFIX}*{SUFFIX}"), key=lambda p: p.name, reverse=True)


def prune(paths: Paths, keep: int = BACKUP_KEEP) -> list[Path]:
    removed = []
    for old in list_backups(paths)[keep:]:
        old.unlink(missing_ok=True)
        removed.append(old)
    return removed


def restore_backup(paths: Paths, backup_file: Path) -> None:
    """Vraća bazu iz kopije. Aplikacija mora biti zatvorena ili konekcije oslobođene pre poziva."""
    src = sqlite3.connect(backup_file)
    dst = sqlite3.connect(paths.db_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
