"""Deljenje u lokalnoj mreži: server u aplikaciji, PIN, komentari, isključivanje linka."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.db.models import RemoteComment
from app.services import sharing
from app.services import tasks as task_service
from app.share.local_server import LocalShareServer
from app.share.snapshot import ShareOptions
from scripts.seed_demo import seed


@pytest.fixture
def served(db):
    with db.session() as s:
        p = seed(s, today=date(2026, 10, 29))
        link = sharing.enable_local(s, p.id, ShareOptions(True, True, False), pin="")
        s.commit()
        pid, token = p.id, link.token
    events: list[str] = []
    server = LocalShareServer(db, 0, host="127.0.0.1", on_comment=events.append)
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    with httpx.Client(base_url=base, follow_redirects=False, timeout=5) as client:
        yield db, client, pid, token, events
    server.stop()


def test_mode_and_port_defaults(session):
    assert sharing.mode(session) == "lan"
    assert sharing.lan_port(session) == sharing.DEFAULT_PORT
    sharing.set_lan_port(session, 9000)
    assert sharing.lan_port(session) == 9000
    with pytest.raises(ValueError):
        sharing.set_lan_port(session, 80)
    sharing.set_mode(session, "cloud")
    assert sharing.mode(session) == "cloud"


def test_page_is_live_and_hides_budget(served):
    db, client, pid, token, _ = served
    r = client.get(f"/p/{token}")
    assert r.status_code == 200
    assert "Onboarding partnera AlfaPay (demo)" in r.text
    assert "Content-Security-Policy" in r.headers
    # stranica se pravi iz baze pri svakom otvaranju: izmena se vidi odmah, bez objave
    with db.session() as s:
        t = next(t for t, _ in task_service.tree(s, pid) if t.title == "Razvoj integracije")
        task_service.update(s, t, title="Razvoj integracije i CMS")
        s.commit()
    assert "Razvoj integracije i CMS" in client.get(f"/p/{token}").text
    assert client.get("/p/nepostojeci-token-123").status_code == 404


def test_comments_go_straight_to_database(served):
    db, client, pid, token, events = served
    with db.session() as s:
        task_id = next(t.id for t, _ in task_service.tree(s, pid))
    r = client.post(
        f"/api/comments/{token}", json={"author": "Marko", "text": "Super!", "task_id": task_id}
    )
    assert r.status_code == 201
    assert events == [pid]
    with db.session() as s:
        c = s.query(RemoteComment).one()
        assert (c.author_name, c.text, c.task_id, c.read) == ("Marko", "Super!", task_id, False)
        assert sharing.unread_count(s, pid) == 1
    shown = client.get(f"/api/comments/{token}").json()["comments"]
    assert shown[0]["author"] == "Marko" and "id" not in shown[0]
    assert client.post(f"/api/comments/{token}", json={"text": "  "}).status_code == 400
    assert (
        client.post(
            f"/api/comments/{token}",
            content=b"x" * 20_000,
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_pin_protects_page_and_comments(served):
    db, client, pid, token, _ = served
    with db.session() as s:
        sharing.enable_local(s, pid, pin="4321")
        s.commit()
    r = client.get(f"/p/{token}")
    assert r.status_code == 200 and "Unesi PIN" in r.text
    assert client.get(f"/api/comments/{token}").status_code == 403
    assert client.post(f"/p/{token}/unlock", data={"pin": "0000"}).status_code == 403
    ok = client.post(f"/p/{token}/unlock", data={"pin": "4321"})
    assert ok.status_code == 303 and "HttpOnly" in ok.headers["set-cookie"]
    assert "Onboarding partnera AlfaPay (demo)" in client.get(f"/p/{token}").text
    assert client.get(f"/api/comments/{token}").status_code == 200


def test_pin_guessing_is_limited(served):
    db, client, pid, token, _ = served
    with db.session() as s:
        sharing.enable_local(s, pid, pin="4321")
        s.commit()
    for _ in range(10):
        client.post(f"/p/{token}/unlock", data={"pin": "1111"})
    blocked = client.post(f"/p/{token}/unlock", data={"pin": "4321"})
    assert blocked.status_code == 429


def test_disabled_link_stops_working(served):
    db, client, pid, token, _ = served
    with db.session() as s:
        sharing.disable_local(s, sharing.active_link(s, pid))
        s.commit()
        assert not sharing.has_live_links(s)
    assert client.get(f"/p/{token}").status_code == 404
    assert client.post(f"/api/comments/{token}", json={"text": "x"}).status_code == 404


def test_cookie_does_not_reveal_pin_hash_and_csrf_blocked(served):
    db, client, pid, token, _ = served
    with db.session() as s:
        sharing.enable_local(s, pid, pin="4321")
        s.commit()
        pin_hash = sharing.active_link(s, pid).pin_hash
    ok = client.post(f"/p/{token}/unlock", data={"pin": "4321"})
    assert pin_hash not in ok.headers["set-cookie"]
    # obična forma ili text/plain (npr. sa druge stranice) ne može da pošalje komentar
    r = client.post(
        f"/api/comments/{token}", content='{"text": "x"}', headers={"Content-Type": "text/plain"}
    )
    assert r.status_code == 415
    assert client.post(f"/api/comments/{token}", json={"text": "ok"}).status_code == 201
    # promena PIN-a poništava stari kolačić
    with db.session() as s:
        sharing.enable_local(s, pid, pin="9999")
        s.commit()
    assert "Unesi PIN" in client.get(f"/p/{token}").text


def test_slow_connection_is_closed(served, monkeypatch):
    import socket

    from app.share import local_server

    db, client, *_ = served
    monkeypatch.setattr(local_server._Handler, "timeout", 1)
    port = int(str(client.base_url).rsplit(":", 1)[1])
    sock = socket.create_connection(("127.0.0.1", port))
    sock.settimeout(5)
    assert sock.recv(10) == b""  # server zatvara vezu koja ništa ne šalje
    sock.close()
