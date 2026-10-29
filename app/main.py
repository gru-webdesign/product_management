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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)

    try:
        db = bootstrap()
    except Exception as exc:  # prikaži grešku umesto tihog gašenja
        log.exception("Pokretanje nije uspelo")
        QMessageBox.critical(None, APP_NAME, f"Baza podataka nije mogla da se otvori:\n\n{exc}")
        return 1

    from app.ui.main_window import MainWindow

    window = MainWindow(db)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
