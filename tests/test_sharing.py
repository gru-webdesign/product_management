"""Deljenje: snimak, HTML, klijent i servis protiv lažnog Worker-a (httpx MockTransport)."""

from __future__ import annotations

import json
import re
from datetime import date

import httpx
import pytest

from app.db.models import RemoteComment
from app.services import projects as projects_svc
from app.services import sharing
from app.services import tasks as tasks_svc
from app.share import render, snapshot
from app.share.client import ShareClient, ShareError, normalize_url
from app.share.snapshot import ShareOptions
from scripts.seed_demo import seed

KEY = "k" * 32


class FakeWorker:
    """Ponaša se kao share_worker/src/index.js za potrebe aplikacije."""

    def __init__(self):
        self.snapshots: dict[str, dict] = {}
        self.comments: dict[str, list[dict]] = {}
        self.fail = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            raise self.fail
        if request.headers.get("authorization") != f"Bearer {KEY}":
            return httpx.Response(401, json={"error": "Neovlašćen pristup."})
        parts = request.url.path.strip("/").split("/")
        if parts[:3] == ["api", "admin", "ping"]:
            return httpx.Response(200, json={"ok": True, "version": "1.0.0"})
        token = parts[3] if len(parts) > 3 else ""
        if parts[2] == "snapshots" and request.method == "PUT":
            self.snapshots[token] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True})
        if parts[2] == "snapshots" and request.method == "DELETE":
            self.snapshots.pop(token, None)
            self.comments.pop(token, None)
            return httpx.Response(200, json={"ok": True})
        if parts[2] == "comments":
            return httpx.Response(200, json={"comments": self.comments.get(token, [])})
        return httpx.Response(404, json={"error": "x"})


@pytest.fixture
def worker():
    return FakeWorker()


@pytest.fixture
def client(worker):
    return ShareClient("https://etapa.test.workers.dev", KEY, transport=httpx.MockTransport(worker))


@pytest.fixture
def project(session):
    p = seed(session, today=date(2026, 11, 2))
    session.flush()
    return p


def test_snapshot_contains_only_shared_data(session, project):
    data = snapshot.build(session, project.id, ShareOptions(), today=date(2026, 11, 2))
    assert data["project"]["name"] == project.name
    assert len(data["tasks"]) == 10 and len(data["deps"]) == 8 and len(data["milestones"]) == 2
    assert "budget" not in data
    dumped = json.dumps(data, ensure_ascii=False)
    assert "Klijent želi toplije boje" not in dumped  # beleške se ne dele
    assert "Foto banka" not in dumped  # dobavljači se ne dele
    with_budget = snapshot.build(session, project.id, ShareOptions(show_budget=True))
    assert with_budget["budget"]["planned"] == "222.000,00 RSD"
    assert len(with_budget["budget"]["lines"]) == 4


def test_render_escapes_script_breakout(session, project):
    tasks_svc.create(session, project.id, title="</script><script>alert(1)</script>")
    html = render.render(snapshot.build(session, project.id, ShareOptions()))
    assert html.count("</script>") == 2  # samo naša dva taga
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(m.group(1))
    assert any(t["title"].startswith("</script>") for t in data["tasks"])
    assert "<title>Redizajn sajta — demo · pregled projekta</title>" in html


def test_publish_update_pin_and_revoke(session, project, client, worker):
    link = sharing.publish(session, client, project.id, ShareOptions(show_budget=True), pin="")
    token = link.token
    assert len(token) >= 16 and link.url == f"https://etapa.test.workers.dev/p/{token}"
    assert worker.snapshots[token]["pin_hash"] == ""
    assert "222.000,00 RSD" in worker.snapshots[token]["html"]

    again = sharing.publish(session, client, project.id, pin="4821")
    assert again.id == link.id and again.token == token  # isti link, novi sadržaj
    assert worker.snapshots[token]["pin_hash"] == sharing.pin_hash(token, "4821")
    sharing.publish(session, client, project.id)  # pin=None zadržava PIN
    assert worker.snapshots[token]["pin_hash"] == sharing.pin_hash(token, "4821")

    with pytest.raises(ValueError):
        sharing.publish(session, client, project.id, pin="12")
    with pytest.raises(ValueError):
        sharing.publish(session, client, project.id, ShareOptions(False, False, False))

    sharing.revoke(session, client, link)
    assert token not in worker.snapshots and link.revoked
    fresh = sharing.publish(session, client, project.id)
    assert fresh.token != token  # posle opoziva novi link


def test_sync_comments(session, project, client, worker):
    link = sharing.publish(session, client, project.id)
    design = next(t for t, _ in tasks_svc.tree(session, project.id) if t.title == "Vizuelni dizajn")
    worker.comments[link.token] = [
        {
            "id": "2026-11-02T10:00:00.000Z-aa",
            "author": "Marko",
            "text": "Može veći logo?",
            "task_id": design.id,
            "posted_at": "2026-11-02T10:00:00.000Z",
        },
        {
            "id": "2026-11-02T11:00:00.000Z-bb",
            "author": "Gost",
            "text": "Super!",
            "task_id": "00000000-0000-0000-0000-000000000000",
            "posted_at": "2026-11-02T11:00:00Z",
        },
    ]
    assert sharing.sync_comments(session, client, link) == 2
    assert sharing.sync_comments(session, client, link) == 0  # bez duplikata
    assert sharing.unread_count(session, project.id) == 2
    on_task = sharing.comments(session, project.id, task_id=design.id)
    assert [c.author_name for c in on_task] == ["Marko"]
    unknown = session.query(RemoteComment).filter_by(author_name="Gost").one()
    assert unknown.task_id is None
    sharing.set_resolved(session, unknown, True)
    assert len(sharing.comments(session, project.id, include_resolved=False)) == 1
    sharing.mark_read(session, project.id)
    assert sharing.unread_count(session, project.id) == 0
    assert sharing.sync_all(session, client) == 0


def test_client_errors(worker):
    bad_key = ShareClient("https://x.workers.dev", "z" * 20, transport=httpx.MockTransport(worker))
    with pytest.raises(ShareError, match="tajni ključ"):
        bad_key.ping()
    worker.fail = httpx.ConnectError("no route")
    good = ShareClient("https://x.workers.dev", KEY, transport=httpx.MockTransport(worker))
    with pytest.raises(ShareError, match="Nema veze"):
        good.ping()
    with pytest.raises(ShareError):
        ShareClient("https://x.workers.dev", "kratak")
    with pytest.raises(ShareError, match="https"):
        normalize_url("http://x.workers.dev")
    assert normalize_url("etapa.me.workers.dev/") == "https://etapa.me.workers.dev"


def test_config_and_keyring(session):
    assert not sharing.configured(session)
    with pytest.raises(ShareError, match="nije podešeno"):
        sharing.make_client(session)
    assert sharing.save_config(session, "etapa.me.workers.dev", KEY) is True
    assert sharing.configured(session)
    assert sharing.worker_url(session) == "https://etapa.me.workers.dev"
    client = sharing.make_client(session)
    assert client.base_url == "https://etapa.me.workers.dev"


def test_publish_requires_existing_project(session, client):
    p = projects_svc.create(session, name="Prazan")
    link = sharing.publish(session, client, p.id)
    assert link.last_published_at is not None
