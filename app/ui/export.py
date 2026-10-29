"""Izvoz projekta: zadaci/troškovi u CSV, ceo projekat u Excel i PDF izveštaj."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget
from sqlalchemy.orm import Session

from app.services import export_csv, export_xlsx
from app.services import projects as project_service
from app.ui.context import AppContext


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "projekat"


def _ask_path(
    ctx: AppContext, parent: QWidget | None, title: str, suffix: str, filters: str, ext: str
) -> tuple[Path, str] | None:
    with ctx.session() as s:
        name = _safe(project_service.get(s, ctx.project_id).name)
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    path, chosen = QFileDialog.getSaveFileName(
        parent, title, str(Path(docs) / f"{name}{suffix}{ext}"), filters
    )
    if not path:
        return None
    target = Path(path)
    if target.suffix.lower() != ext:
        target = target.with_suffix(ext)
    return target, chosen


def _save(
    ctx: AppContext, parent: QWidget | None, target: Path, write: Callable[[Session], object]
) -> Path | None:
    QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        with ctx.session() as s:
            write(s)
    except OSError as exc:
        QGuiApplication.restoreOverrideCursor()
        QMessageBox.warning(parent, "Izvoz nije uspeo", f"Fajl nije sačuvan.\n\n{exc}")
        return None
    QGuiApplication.restoreOverrideCursor()
    ctx.notify(f"Sačuvano: {target}")
    return target


def export_tasks_dialog(ctx: AppContext, parent: QWidget | None = None) -> Path | None:
    if not ctx.project_id:
        return None
    picked = _ask_path(
        ctx,
        parent,
        "Izvezi u CSV",
        " - zadaci",
        "Zadaci (*.csv);;Troškovi i prihodi (*.csv)",
        ".csv",
    )
    if not picked:
        return None
    target, chosen = picked
    pid = ctx.project_id
    costs = chosen.startswith("Troškovi")

    def write(s: Session) -> None:
        text = export_csv.costs_csv(s, pid) if costs else export_csv.tasks_csv(s, pid)
        export_csv.write(target, text)

    return _save(ctx, parent, target, write)


def export_xlsx_dialog(ctx: AppContext, parent: QWidget | None = None) -> Path | None:
    if not ctx.project_id:
        return None
    picked = _ask_path(ctx, parent, "Izvezi u Excel", "", "Excel radna sveska (*.xlsx)", ".xlsx")
    if not picked:
        return None
    target, pid = picked[0], ctx.project_id
    return _save(ctx, parent, target, lambda s: export_xlsx.write(s, pid, target))


def export_pdf_dialog(ctx: AppContext, parent: QWidget | None = None) -> Path | None:
    if not ctx.project_id:
        return None
    picked = _ask_path(ctx, parent, "PDF izveštaj", " - izveštaj", "PDF (*.pdf)", ".pdf")
    if not picked:
        return None
    from app.ui.report import write_pdf

    target, pid = picked[0], ctx.project_id
    return _save(ctx, parent, target, lambda s: write_pdf(s, pid, target))
