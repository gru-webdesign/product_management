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
    from app.main import bootstrap, set_locale
    from app.ui import theme
    from app.ui.main_window import MainWindow
    from scripts.seed_demo import seed

    app = QApplication(sys.argv)
    set_locale()
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

    from app.services import tasks as task_service
    from app.ui.dialogs.task_dialog import TaskDialog

    with db.session() as s:
        design = next(
            t
            for t, _ in task_service.tree(s, window.ctx.project_id)
            if t.title == "Vizuelni dizajn"
        )
        design_id = design.id
    for tab, label in ((0, "detalji"), (2, "zavisnosti")):
        dlg = TaskDialog(window.ctx, design_id, window)
        dlg.tabs.setCurrentIndex(tab)
        dlg.show()
        for _ in range(5):
            app.processEvents()
        path = out / f"dialog-{label}{suffix}.png"
        dlg.grab().save(str(path))
        dlg.close()
        print(path)
    from app.ui.dialogs.budget_dialog import BudgetDialog
    from app.ui.dialogs.cost_dialog import MoneyEntryDialog
    from app.ui.dialogs.project_dialog import ProjectDialog
    from app.ui.dialogs.settings_dialog import SettingsDialog
    from app.ui.dialogs.share_dialog import ShareDialog

    dialogs = {
        "share": lambda: ShareDialog(window.ctx, window),
        "settings": lambda: SettingsDialog(window.ctx, window),
        "settings-share": lambda: SettingsDialog(window.ctx, window, tab="share"),
        "cost": lambda: MoneyEntryDialog(window.ctx, "cost", None, window),
        "budget": lambda: BudgetDialog(window.ctx, window),
        "project": lambda: ProjectDialog(None, window),
    }
    for name, make in dialogs.items():
        dlg = make()
        dlg.show()
        for _ in range(5):
            app.processEvents()
        path = out / f"dialog-{name}{suffix}.png"
        dlg.grab().save(str(path))
        dlg.close()
        print(path)

    # prazan ekran (nema projekata)
    empty_db = bootstrap(get_paths(Path(tempfile.mkdtemp(prefix="etapa-empty-"))))
    empty = MainWindow(empty_db)
    empty.resize(1100, 700)
    empty.show()
    for _ in range(5):
        app.processEvents()
    empty.grab().save(str(out / f"0-empty{suffix}.png"))
    print(out / f"0-empty{suffix}.png")
    empty.close()
    empty_db.dispose()
    db.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
