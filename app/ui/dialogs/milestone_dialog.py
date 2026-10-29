"""Dijalog za milestone (naziv, datum, ostvaren)."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QCheckBox, QLineEdit, QMessageBox, QPushButton

from app.services import milestones as ms_service
from app.ui.context import AppContext
from app.ui.dialogs.base import FormDialog
from app.ui.widgets.fields import date_edit, from_qdate


class MilestoneDialog(FormDialog):
    def __init__(
        self, ctx: AppContext, milestone_id: str | None = None, parent=None, on: date | None = None
    ) -> None:
        super().__init__("Milestone" if milestone_id else "Novi milestone", parent)
        self.ctx = ctx
        self.milestone_id = milestone_id
        name, day, done = "", on or date.today(), False
        if milestone_id:
            from app.db.models import Milestone

            with ctx.session() as s:
                m = s.get(Milestone, milestone_id)
                name, day, done = m.name, m.date, m.done
        self.name = QLineEdit(name)
        self.name.setPlaceholderText("npr. Dizajn odobren")
        self.day = date_edit(day)
        self.done_box = QCheckBox("Ostvaren")
        self.done_box.setChecked(done)
        self.form.addRow("Naziv", self.name)
        self.form.addRow("Datum", self.day)
        self.form.addRow("", self.done_box)
        if milestone_id:
            delete = QPushButton("Obriši")
            delete.setProperty("danger", True)
            delete.clicked.connect(self._delete)
            self.buttons.addButton(delete, self.buttons.ButtonRole.DestructiveRole)

    def validate(self) -> None:
        if not self.name.text().strip():
            raise ValueError("Unesi naziv.")

    def save(self) -> bool:
        name, day, done = self.name.text(), from_qdate(self.day.date()), self.done_box.isChecked()
        pid = self.ctx.project_id

        def work(s):
            from app.db.models import Milestone

            if self.milestone_id:
                ms_service.update(
                    s, s.get(Milestone, self.milestone_id), name=name, date=day, done=done
                )
            else:
                ms_service.create(s, pid, name, day, done)
            return True

        return bool(self.ctx.run(work, self))

    def _delete(self) -> None:
        if (
            QMessageBox.question(self, "Obriši", "Obrisati milestone?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        from app.db.models import Milestone

        self.ctx.run(lambda s: ms_service.delete(s, s.get(Milestone, self.milestone_id)), self)
        self.done(2)


def edit_milestone(
    ctx: AppContext, milestone_id: str | None, parent=None, on: date | None = None
) -> None:
    dlg = MilestoneDialog(ctx, milestone_id, parent, on)
    if dlg.exec() == dlg.DialogCode.Accepted:
        dlg.save()
