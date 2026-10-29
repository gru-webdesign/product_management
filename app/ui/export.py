"""Dijalog za izvoz zadataka i troškova u CSV."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from app.services import export_csv
from app.services import projects as project_service
from app.ui.context import AppContext


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "projekat"


def export_tasks_dialog(ctx: AppContext, parent: QWidget | None = None) -> Path | None:
    pid = ctx.project_id
    if not pid:
        return None
    with ctx.session() as s:
        name = _safe(project_service.get(s, pid).name)
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    path, chosen = QFileDialog.getSaveFileName(
        parent,
        "Izvezi u CSV",
        str(Path(docs) / f"{name} - zadaci.csv"),
        "Zadaci (*.csv);;Troškovi i prihodi (*.csv)",
    )
    if not path:
        return None
    target = Path(path)
    if target.suffix.lower() != ".csv":
        target = target.with_suffix(".csv")
    costs = chosen.startswith("Troškovi")
    with ctx.session() as s:
        text = export_csv.costs_csv(s, pid) if costs else export_csv.tasks_csv(s, pid)
    try:
        export_csv.write(target, text)
    except OSError as exc:
        QMessageBox.warning(parent, "Izvoz nije uspeo", str(exc))
        return None
    ctx.notify(f"Sačuvano: {target}")
    return target
