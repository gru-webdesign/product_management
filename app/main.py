"""Ulaz u aplikaciju: priprema podataka (migracije, backup) pa glavni prozor."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app import APP_NAME, __version__
from app.config import get_paths
from app.db.base import Database
from app.services import backup
from app.services.defaults import ensure_defaults

log = logging.getLogger(__name__)


def bootstrap(paths=None) -> Database:
    """Priprema bazu: backup postojeće, migracije na najnoviju verziju, podrazumevani podaci."""
    paths = (paths or get_paths()).ensure()
    if paths.db_path.exists():
        backup.create_backup(paths)
    db = Database(paths)
    db.upgrade()
    with db.session() as s:
        ensure_defaults(s)
        s.commit()
    return db


def set_locale() -> None:
    """Srpski (latinica) format brojeva i datuma: decimalni zarez, tačka za hiljade."""
    from PySide6.QtCore import QLocale

    locale = QLocale(QLocale.Language.Serbian, QLocale.Script.LatinScript, QLocale.Country.Serbia)
    QLocale.setDefault(locale)


def _offer_recovery(reason: str) -> bool:
    """Baza je oštećena: ponudi vraćanje poslednje ispravne kopije."""
    paths = get_paths()
    good = [b for b in backup.list_backups(paths)]
    text = f"Baza podataka je oštećena i ne može da se otvori.\n\nDetalji: {reason}\n\n" + (
        "Vratiti najnoviju ispravnu automatsku kopiju? Oštećeni fajl se ne briše, nego se "
        "čuva u folderu sa podacima."
        if good
        else "Nema automatskih kopija. Napraviti novu praznu bazu? Oštećeni fajl se čuva "
        "u folderu sa podacima."
    )
    answer = QMessageBox.question(None, APP_NAME, text)
    if answer != QMessageBox.StandardButton.Yes:
        return False
    used = backup.recover(paths)
    QMessageBox.information(
        None,
        APP_NAME,
        f"Baza je vraćena iz kopije {used.name}." if used else "Napravljena je nova prazna baza.",
    )
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("alembic").setLevel(logging.WARNING)
    app = QApplication(sys.argv)
    set_locale()
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    from pathlib import Path

    from PySide6.QtGui import QIcon

    app.setWindowIcon(QIcon(str(Path(__file__).parent / "resources" / "icons" / "app.png")))

    try:
        try:
            db = bootstrap()
        except backup.CorruptDatabase as exc:
            if not _offer_recovery(str(exc)):
                return 1
            db = bootstrap()
    except Exception as exc:  # prikaži grešku umesto tihog gašenja
        log.exception("Pokretanje nije uspelo")
        QMessageBox.critical(None, APP_NAME, f"Baza podataka nije mogla da se otvori:\n\n{exc}")
        return 1

    from PySide6.QtCore import QLockFile

    lock = QLockFile(str(db.paths.lock_path))
    lock.setStaleLockTime(0)
    lock.tryLock(100)  # samo oznaka da je aplikacija otvorena; ne sprečava pokretanje

    from app.ui import theme
    from app.ui.main_window import MainWindow, initial_theme

    theme.load_fonts(app)
    theme.apply(app, initial_theme(db))
    window = MainWindow(db)
    window.show()
    from PySide6.QtCore import QTimer

    if "--smoke-test" in sys.argv:  # provera gotovog .exe-a: pokreni, otvori prozor, zatvori
        QTimer.singleShot(1500, app.quit)
    else:
        QTimer.singleShot(1500, window.sync_comments_in_background)
        QTimer.singleShot(3000, window.reminders.check)
    code = app.exec()
    from app.ui import background

    background.wait_all(5000)
    db.dispose()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
