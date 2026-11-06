"""Server za deljenje u lokalnoj mreži: Etapa sama služi stranicu projekta, bez interneta.

Iste adrese kao Cloudflare Worker, pa stranica (templates/share.html) radi bez izmena:
  GET  /p/<token>                 stranica (PIN forma ako je postavljen)
  POST /p/<token>/unlock          provera PIN-a → kolačić
  GET  /api/comments/<token>      komentari za prikaz
  POST /api/comments/<token>      novi komentar {author, text, task_id}

Radi u pozadinskoj niti; svaki zahtev otvara svoju sesiju baze. Ne importuje Qt.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import socket
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from html import escape
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from app.db.base import Database
from app.services import sharing

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
TASK_RE = re.compile(r"^[0-9a-f-]{36}$")
MAX_BODY = 16_384
COMMENTS_PER_MINUTE = 8
PIN_TRIES = 10  # pogrešnih PIN-ova po adresi u PIN_WINDOW sekundi
PIN_WINDOW = 600

CSP = "; ".join(
    [
        "default-src 'none'",
        "script-src 'unsafe-inline'",
        "style-src 'unsafe-inline'",
        "img-src data:",
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
    ]
)


def local_ip() -> str:
    """Adresa ovog računara u lokalnoj mreži (bez slanja ikakvih podataka)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # UDP connect samo bira mrežni interfejs
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def simple_page(title: str, text: str, extra: str = "") -> str:
    return f"""<!doctype html><html lang="sr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)}</title>
<style>body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#F2F4F9;
color:#0E1730;display:grid;place-items:center;min-height:100vh;margin:0;padding:16px}}
.box{{background:#fff;border:1px solid #E3E7F0;border-radius:12px;padding:28px;max-width:380px;
width:100%;box-shadow:0 8px 24px rgba(19,34,79,.08)}}h1{{font-size:18px;margin:0 0 8px}}
p{{color:#5A6480;margin:0 0 16px;line-height:1.5}}input{{width:100%;box-sizing:border-box;
padding:10px 12px;border:1px solid #CCD3E2;border-radius:8px;font-size:16px}}
button{{margin-top:12px;width:100%;padding:10px;border:0;border-radius:8px;background:#13224F;
color:#fff;font-weight:600;font-size:15px;cursor:pointer}}.err{{color:#D23434;margin-top:10px}}
@media (prefers-color-scheme:dark){{body{{background:#0A1128;color:#F3F5FB}}
.box{{background:#111B38;border-color:#1E2B52}}p{{color:#9CA7C6}}
input{{background:#0A1128;color:#F3F5FB;border-color:#2B3B68}}
button{{background:#fff;color:#0A1128}}}}</style></head>
<body><div class="box"><h1>{escape(title)}</h1><p>{escape(text)}</p>{extra}</div></body></html>"""


class _Limiter:
    """Brojač događaja po adresi u kliznom prozoru (zaštita od pogađanja PIN-a i spama)."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            return len(q) >= self.limit

    def hit(self, key: str) -> None:
        with self.lock:
            self.hits[key].append(time.monotonic())


def _cookie_secret(db: Database) -> bytes:
    """Tajna za kolačić posle PIN-a; čuva se u bazi da kolačić važi i posle restarta."""
    from app.services.defaults import get_setting, set_setting

    with db.session() as s:
        value = get_setting(s, "share.cookie_secret")
        if not value:
            value = secrets.token_hex(32)
            set_setting(s, "share.cookie_secret", value)
            s.commit()
    return bytes.fromhex(value)


def cookie_value(secret: bytes, token: str, pin_hash: str) -> str:
    """Kolačić ne otkriva PIN ni njegov heš; promena PIN-a ga poništava."""
    return hmac.new(secret, f"{token}:{pin_hash}".encode(), hashlib.sha256).hexdigest()


class LocalShareServer:
    """HTTP server u pozadinskoj niti. on_comment(project_id) se zove iz te niti."""

    def __init__(
        self,
        db: Database,
        port: int,
        host: str = "0.0.0.0",
        on_comment: Callable[[str], None] | None = None,
    ) -> None:
        self.db = db
        self.on_comment = on_comment
        self.pin_limiter = _Limiter(PIN_TRIES, PIN_WINDOW)
        self.comment_limiter = _Limiter(COMMENTS_PER_MINUTE, 60)
        self.secret = _cookie_secret(db)
        handler = type("Handler", (_Handler,), {"app": self})
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    def url(self, token: str, ip: str | None = None) -> str:
        return f"http://{ip or local_ip()}:{self.port}/p/{token}"

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, name="etapa-share", daemon=True
        )
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
            self.thread = None


class _Handler(BaseHTTPRequestHandler):
    app: LocalShareServer
    server_version = "Etapa"
    sys_version = ""
    timeout = 15  # spora ili prazna veza se zatvara, ne drži nit zauvek

    def log_message(self, format, *args) -> None:  # noqa: A002 (potpis iz biblioteke)
        pass  # bez ispisa u konzolu

    # --- odgovori --------------------------------------------------------------------------------

    def _send(self, status: int, body: str, ctype: str, extra: dict | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype == "text/html":
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Frame-Options", "DENY")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _html(self, body: str, status: int = 200, extra: dict | None = None) -> None:
        self._send(status, body, "text/html", extra)

    def _json(self, data: dict, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False), "application/json")

    def _not_found(self) -> None:
        self._html(
            simple_page(
                "Link nije dostupan", "Ovaj link ne postoji ili ga je vlasnik projekta isključio."
            ),
            404,
        )

    def _pin_page(self, token: str, wrong: bool = False, blocked: bool = False) -> None:
        msg = ""
        if blocked:
            msg = '<div class="err">Previše pokušaja. Pokušaj ponovo za 10 minuta.</div>'
        elif wrong:
            msg = '<div class="err">PIN nije tačan.</div>'
        form = (
            f'<form method="post" action="/p/{token}/unlock">'
            '<input name="pin" type="password" autocomplete="off" placeholder="PIN" autofocus '
            f'required maxlength="32"><button type="submit">Otvori</button>{msg}</form>'
        )
        status = 429 if blocked else (403 if wrong else 200)
        self._html(
            simple_page("Zaštićen pregled projekta", "Unesi PIN koji si dobio uz link.", form),
            status,
        )

    # --- pomoćne ---------------------------------------------------------------------------------

    def _client(self) -> str:
        return self.client_address[0]

    def _body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length < 0 or length > MAX_BODY:
            return None
        return self.rfile.read(length)

    def _unlocked(self, link) -> bool:
        if not link.pin_hash:
            return True
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        morsel = cookie.get(f"etapa_{link.token}")
        expected = cookie_value(self.app.secret, link.token, link.pin_hash)
        return bool(morsel) and secrets.compare_digest(morsel.value, expected)

    def _route(self) -> tuple[str, str, str]:
        path = self.path.split("?", 1)[0]
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "p" and TOKEN_RE.match(parts[1]):
            sub = parts[2] if len(parts) > 2 else ""
            if len(parts) <= 3:
                return "page", parts[1], sub
        if len(parts) == 3 and parts[:2] == ["api", "comments"] and TOKEN_RE.match(parts[2]):
            return "comments", parts[2], ""
        if not parts:
            return "root", "", ""
        return "", "", ""

    # --- metode ----------------------------------------------------------------------------------

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        kind, token, sub = self._route()
        if kind == "root":
            self._html(simple_page("Etapa", "Ovde se otvaraju linkovi za pregled projekata."))
            return
        if kind not in ("page", "comments") or sub:
            self._not_found()
            return
        with self.app.db.session() as s:
            link = sharing.live_link(s, token)
            if link is None:
                if kind == "page":
                    self._not_found()
                else:
                    self._json({"error": "Link nije dostupan."}, 404)
                return
            if not self._unlocked(link):
                if kind == "page":
                    self._pin_page(token)
                else:
                    self._json({"error": "Potreban je PIN."}, 403)
                return
            if kind == "page":
                self._html(sharing.page_html(s, link))
            else:
                self._json({"comments": sharing.public_comments(s, link)})

    def do_POST(self) -> None:  # noqa: N802
        kind, token, sub = self._route()
        if kind == "page" and sub == "unlock":
            self._unlock(token)
        elif kind == "comments":
            self._post_comment(token)
        else:
            self._not_found()

    def _unlock(self, token: str) -> None:
        ip = self._client()
        if self.app.pin_limiter.blocked(ip):
            self._pin_page(token, blocked=True)
            return
        body = self._body()
        pin = ""
        if body is not None:
            pin = (parse_qs(body.decode("utf-8", "replace")).get("pin") or [""])[0]
        with self.app.db.session() as s:
            link = sharing.live_link(s, token)
            if link is None:
                self._not_found()
                return
            if not link.pin_hash or not sharing.check_pin(link, pin):
                self.app.pin_limiter.hit(ip)
                self._pin_page(token, wrong=True)
                return
            value = cookie_value(self.app.secret, link.token, link.pin_hash)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/p/{token}")
        self.send_header(
            "Set-Cookie",
            f"etapa_{token}={value}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax",
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _post_comment(self, token: str) -> None:
        ip = self._client()
        if self.app.comment_limiter.blocked(ip):
            self._json(
                {"error": "Previše komentara za kratko vreme, pokušaj ponovo za minut."}, 429
            )
            return
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            # obična forma ili text/plain sa druge stranice (CSRF) ne prolazi
            self._json({"error": "Neispravan zahtev."}, 415)
            return
        body = self._body()
        if body is None:
            self._json({"error": "Komentar je prevelik."}, 413)
            return
        try:
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._json({"error": "Neispravan zahtev."}, 400)
            return
        task_id = data.get("task_id")
        task_id = str(task_id) if task_id else None
        if task_id and not TASK_RE.match(task_id):
            self._json({"error": "Nepoznat zadatak."}, 400)
            return
        with self.app.db.session() as s:
            link = sharing.live_link(s, token)
            if link is None:
                self._json({"error": "Link nije dostupan."}, 404)
                return
            if not self._unlocked(link):
                self._json({"error": "Potreban je PIN."}, 403)
                return
            try:
                comment = sharing.add_local_comment(
                    s, link, str(data.get("author") or ""), str(data.get("text") or ""), task_id
                )
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
                return
            s.commit()
            project_id, cid = link.project_id, comment.remote_id
        self.app.comment_limiter.hit(ip)
        self._json({"ok": True, "id": cid}, 201)
        if self.app.on_comment is not None:
            try:
                self.app.on_comment(project_id)
            except Exception:  # obaveštenje UI-ja ne sme da obori server
                pass
