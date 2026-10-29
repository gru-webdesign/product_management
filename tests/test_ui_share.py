from __future__ import annotations

import csv
import io
from datetime import date

import httpx
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.services import export_csv, sharing
from app.services import tasks as task_service
from app.services.defaults import get_setting
from app.share.client import ShareClient
from app.ui import theme
from app.ui.dialogs.settings_dialog import SettingsDialog
from app.ui.dialogs.share_dialog import ShareDialog
from app.ui.main_window import MainWindow
from scripts.seed_demo import seed
from tests.test_sharing import KEY, FakeWorker


@pytest.fixture
def setup(qtbot, db, monkeypatch):
    with db.session() as s:
        seed(s, today=date.today())
        s.commit()
    worker = FakeWorker()
    real = sharing.make_client

    def fake_make_client(session, transport=None):
        return real(session, transport=httpx.MockTransport(worker))

    monkeypatch.setattr(sharing, "make_client", fake_make_client)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    w = MainWindow(db)
    qtbot.addWidget(w)
    w.show()
    return w, worker


def configure(w):
    w.ctx.run(lambda s: sharing.save_config(s, "https://etapa.test.workers.dev", KEY))


def test_not_configured_shows_setup(setup, qtbot):
    w, _ = setup
    dlg = ShareDialog(w.ctx, w)
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.setup_box.isVisible()
    assert not dlg.publish_button.isEnabled()


def test_publish_pin_comments_and_revoke(setup, qtbot):
    w, worker = setup
    configure(w)
    dlg = ShareDialog(w.ctx, w)
    qtbot.addWidget(dlg)
    dlg.show()
    assert not dlg.setup_box.isVisible()
    dlg.show_budget.setChecked(True)
    dlg.use_pin.setChecked(True)
    dlg._publish()
    assert "Upiši PIN" in dlg.status.text()  # PIN uključen, a nije upisan
    dlg.pin.setText("4821")
    dlg._publish()
    url = dlg.url.text()
    assert url.startswith("https://etapa.test.workers.dev/p/")
    token = url.rsplit("/", 1)[1]
    assert worker.snapshots[token]["pin_hash"] == sharing.pin_hash(token, "4821")
    assert QApplication.clipboard().text() == url
    assert dlg.publish_button.text() == "Ažuriraj link"

    worker.comments[token] = [
        {
            "id": "2026-11-02T10:00:00Z-a",
            "author": "Marko",
            "text": "Super",
            "task_id": None,
            "posted_at": "2026-11-02T10:00:00Z",
        }
    ]
    dlg.comments.sync()
    assert "1" in dlg.comments.status.text()
    assert dlg.comments.list.count() == 1

    dlg._revoke()
    assert token not in worker.snapshots
    assert dlg.url.text() == "" and dlg.publish_button.text() == "Objavi link"


def test_badge_counts_unread(setup, qtbot):
    w, worker = setup
    configure(w)
    with w.db.session() as s:
        link = sharing.publish(s, sharing.make_client(s), w.ctx.project_id)
        s.commit()
        token = link.token
    worker.comments[token] = [
        {
            "id": f"2026-11-02T10:00:0{i}Z-a",
            "author": "Gost",
            "text": f"k{i}",
            "task_id": None,
            "posted_at": f"2026-11-02T10:00:0{i}Z",
        }
        for i in range(2)
    ]
    with w.db.session() as s:
        sharing.sync_all(s, sharing.make_client(s))
        s.commit()
    w.ctx.data_changed.emit()
    assert w.header.share_button.text() == "Podeli · 2 nova komentara"


def test_task_dialog_shows_task_comments(setup, qtbot):
    w, worker = setup
    configure(w)
    from app.ui.dialogs.task_dialog import TaskDialog

    with w.db.session() as s:
        link = sharing.publish(s, sharing.make_client(s), w.ctx.project_id)
        task = next(
            t for t, _ in task_service.tree(s, w.ctx.project_id) if t.title == "Izrada sajta"
        )
        worker.comments[link.token] = [
            {
                "id": "x1",
                "author": "Ana",
                "text": "Kad počinje?",
                "task_id": task.id,
                "posted_at": "2026-11-02T10:00:00Z",
            }
        ]
        sharing.sync_comments(s, sharing.make_client(s), link)
        s.commit()
        tid = task.id
    dlg = TaskDialog(w.ctx, tid, w)
    qtbot.addWidget(dlg)
    assert dlg.comments.list.count() == 1
    assert "Ana" in dlg.comments.list.item(0).text()


def test_settings_save(setup, qtbot):
    w, _ = setup
    dlg = SettingsDialog(w.ctx, w)
    qtbot.addWidget(dlg)
    assert not dlg.base.isEnabled()  # demo ima troškove → valuta zaključana
    dlg.user_name.setText("Goran")
    dlg.rate.setText("2.500")
    dlg.warn.setValue(70)
    dlg.theme.setCurrentIndex(dlg.theme.findData("dark"))
    dlg.worker_url.setText("etapa.me.workers.dev")
    dlg.admin_key.setText(KEY)
    dlg._save()
    with w.db.session() as s:
        assert get_setting(s, "user_name") == "Goran"
        assert get_setting(s, "default_hourly_rate_minor") == "250000"
        assert get_setting(s, "budget_warn_percent") == "70"
        assert sharing.worker_url(s) == "https://etapa.me.workers.dev"
        assert sharing.configured(s)
    assert theme.tokens().name == "dark"


def test_settings_connection_test(setup, qtbot, monkeypatch):
    w, worker = setup
    dlg = SettingsDialog(w.ctx, w, tab="share")
    qtbot.addWidget(dlg)
    assert dlg.tabs.currentIndex() == 1
    real_init = ShareClient.__init__
    monkeypatch.setattr(
        ShareClient,
        "__init__",
        lambda self, url, key, transport=None: real_init(
            self, url, key, httpx.MockTransport(worker)
        ),
    )
    dlg.worker_url.setText("https://etapa.me.workers.dev")
    dlg.admin_key.setText(KEY)
    dlg._test()
    assert "Veza radi" in dlg.test_result.text()
    dlg.admin_key.setText("pogresan-kljuc-123456789")
    dlg._test()
    assert "ključ" in dlg.test_result.text()


def test_csv_export(setup, tmp_path):
    w, _ = setup
    with w.db.session() as s:
        text = export_csv.tasks_csv(s, w.ctx.project_id)
        costs = export_csv.costs_csv(s, w.ctx.project_id)
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert rows[0][1] == "Naziv" and len(rows) == 11
    assert any(r[1].strip() == "Početna stranica" and r[0] == "1" for r in rows)
    cost_rows = list(csv.reader(io.StringIO(costs), delimiter=";"))
    figma = next(r for r in cost_rows if r[4] == "Figma")
    assert figma[5] == "89,00" and figma[6] == "EUR" and figma[8] == "10430,80"
    target = tmp_path / "x.csv"
    export_csv.write(target, text)
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM za Excel
