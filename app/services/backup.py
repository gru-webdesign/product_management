"""Automatske kopije baze.

Pri svakom pokretanju pravi se kopija preko SQLite backup API-ja (bezbedno i u WAL režimu).
Čuva se poslednjih BACKUP_KEEP kopija i još po jedna za svaki od poslednjih DAILY_DAYS dana, pa
ni deset pokretanja zaredom ne briše jučerašnje stanje. Oštećena baza se ne kopira.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import BACKUP_KEEP, Paths

PREFIX = "etapa-"
SUFFIX = ".db"
DAILY_DAYS = 30


class CorruptDatabase(Exception):
    """Baza ne prolazi proveru integriteta (oštećen ili pogrešan fajl)."""


def check(path: Path) -> None:
    """Brza provera da je fajl ispravna SQLite baza; inače CorruptDatabase."""
    try:
        con = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
        try:
            result = con.execute("PRAGMA quick_check").fetchone()
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        raise CorruptDatabase(str(exc)) from exc
    if not result or result[0] != "ok":
        raise CorruptDatabase(str(result[0] if result else "nepoznata greška"))


def create_backup(
    paths: Paths, keep: int = BACKUP_KEEP, now: datetime | None = None
) -> Path | None:
    if not paths.db_path.exists():
        return None
    check(paths.db_path)  # oštećena baza ne sme da istisne dobre kopije
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
    """Briše višak: ostaje poslednjih `keep` i najnovija kopija za svaki od DAILY_DAYS dana."""
    backups = list_backups(paths)  # najnovije prvo
    daily: dict[str, Path] = {}
    for b in backups:
        day = b.name[len(PREFIX) : len(PREFIX) + 8]
        daily.setdefault(day, b)
    kept_days = set(sorted(daily, reverse=True)[:DAILY_DAYS])
    keep_set = set(backups[:keep]) | {daily[d] for d in kept_days}
    removed = []
    for old in backups:
        if old not in keep_set:
            old.unlink(missing_ok=True)
            removed.append(old)
    return removed


def restore_backup(paths: Paths, backup_file: Path) -> None:
    """Vraća bazu iz kopije. Aplikacija mora biti zatvorena ili konekcije oslobođene pre poziva."""
    check(backup_file)  # pre bilo kakve izmene trenutne baze
    src = sqlite3.connect(backup_file)
    dst = sqlite3.connect(paths.db_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def recover(paths: Paths, now: datetime | None = None) -> Path | None:
    """Oštećena baza se sklanja (ne briše se), a vraća se najnovija ispravna kopija.

    Vraća kopiju iz koje je baza vraćena, ili None ako ispravne kopije nema (tada aplikacija
    kreće sa praznom bazom, a oštećeni fajl ostaje sačuvan pored nje).
    """
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(paths.db_path) + suffix)
        if f.exists():
            f.rename(paths.data_dir / f"etapa-ostecena-{stamp}.db{suffix}")
    for candidate in list_backups(paths):
        try:
            check(candidate)
        except CorruptDatabase:
            continue
        restore_backup(paths, candidate)
        return candidate
    return None
