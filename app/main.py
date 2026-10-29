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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    set_locale()
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)

    try:
        db = bootstrap()
    except Exception as exc:  # prikaži grešku umesto tihog gašenja
        log.exception("Pokretanje nije uspelo")
        QMessageBox.critical(None, APP_NAME, f"Baza podataka nije mogla da se otvori:\n\n{exc}")
        return 1

    from app.ui import theme
    from app.ui.main_window import MainWindow, initial_theme

    theme.load_fonts(app)
    theme.apply(app, initial_theme(db))
    window = MainWindow(db)
    window.show()
    from PySide6.QtCore import QTimer

    QTimer.singleShot(1500, window.sync_comments_in_background)
    code = app.exec()
    from app.ui import background

    background.wait_all(5000)
    db.dispose()
    return code


if __name__ == "__main__":
    sys.exit(main())
