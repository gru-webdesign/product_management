"""Snimci ekrana svih prikaza sa demo podacima (za proveru izgleda, radi i bez monitora).

    python scripts/screenshots.py [izlazni_folder] [--dark]

Pravi privremenu demo bazu, otvara glavni prozor i snima svaki tab u PNG.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dark = "--dark" in sys.argv
    out = Path(args[0] if args else "screenshots").resolve()
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication

    from app.config import get_paths
    from app.main import bootstrap
    from app.ui import theme
    from app.ui.main_window import MainWindow
    from scripts.seed_demo import seed

    app = QApplication(sys.argv)
    tmp = tempfile.mkdtemp(prefix="etapa-shots-")
    db = bootstrap(get_paths(Path(tmp)))
    with db.session() as s:
        seed(s, today=date.today())
        s.commit()

    theme.load_fonts(app)
    theme.apply(app, "dark" if dark else "light")
    window = MainWindow(db)
    window.resize(1440, 880)
    window.show()
    app.processEvents()

    suffix = "-dark" if dark else ""
    for i, view in enumerate(window.views):
        window.tabs.setCurrentIndex(i)
        for _ in range(5):
            app.processEvents()
        name = f"{i + 1}-{view.icon_name}{suffix}.png"
        window.grab().save(str(out / name))
        print(out / name)
    db.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
