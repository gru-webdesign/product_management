"""Deljenje projekta linkom: objava snimka, opoziv, komentari gledalaca.

Dva načina (podešavanje `share_mode`):
- "lan" (podrazumevano): Etapa sama služi stranicu u lokalnoj mreži (app/share/local_server.py).
  Ništa ne izlazi iz mreže; stranica se pravi iz baze pri svakom otvaranju, pa je uvek ažurna.
- "cloud": snimak se šalje na korisnikov Cloudflare Worker (share_worker/).
"""

from __future__ import annotations

import hashlib
import secrets as pysecrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import RemoteComment, ShareLink, Task
from app.services import activity
from app.services.defaults import get_setting, set_setting
from app.share import render, snapshot
from app.share.client import ShareClient, ShareError, normalize_url
from app.share.secrets import get_admin_key, set_admin_key
from app.share.snapshot import ShareOptions

URL_SETTING = "share_worker_url"
MODE_SETTING = "share_mode"
PORT_SETTING = "share_lan_port"
DEFAULT_PORT = 8765
MAX_COMMENT = 2000
MAX_AUTHOR = 80
MAX_COMMENTS_PER_LINK = 300


# --- način deljenja ------------------------------------------------------------------------------


def mode(session: Session) -> str:
    return "cloud" if get_setting(session, MODE_SETTING) == "cloud" else "lan"


def set_mode(session: Session, value: str) -> None:
    set_setting(session, MODE_SETTING, "cloud" if value == "cloud" else "lan")


def lan_port(session: Session) -> int:
    try:
        port = int(get_setting(session, PORT_SETTING) or DEFAULT_PORT)
    except ValueError:
        return DEFAULT_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_PORT


def set_lan_port(session: Session, port: int) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("Port mora biti broj od 1024 do 65535.")
    set_setting(session, PORT_SETTING, str(port))


# --- podešavanje Worker-a ------------------------------------------------------------------------


def worker_url(session: Session) -> str:
    return get_setting(session, URL_SETTING)


def configured(session: Session) -> bool:
    return bool(worker_url(session) and get_admin_key(session))


def save_config(session: Session, url: str, admin_key: str | None) -> bool:
    """Čuva adresu (i ključ ako je dat). Vraća True ako je ključ u sistemskom skladištu."""
    set_setting(session, URL_SETTING, normalize_url(url) if url.strip() else "")
    if admin_key is not None:
        return set_admin_key(session, admin_key)
    return True


def make_client(session: Session, transport=None) -> ShareClient:
    url, key = worker_url(session), get_admin_key(session)
    if not url or not key:
        raise ShareError(
            "Deljenje nije podešeno: upiši adresu Worker-a i tajni ključ u Podešavanja → Deljenje."
        )
    return ShareClient(url, key, transport=transport)


# --- linkovi -------------------------------------------------------------------------------------


def new_token() -> str:
    return pysecrets.token_urlsafe(12)


def pin_hash(token: str, pin: str) -> str:
    return hashlib.sha256(f"{token}:{pin}".encode()).hexdigest()


def active_link(session: Session, project_id: str) -> ShareLink | None:
    return session.scalar(
        select(ShareLink)
        .where(ShareLink.project_id == project_id, ShareLink.revoked.is_(False))
        .order_by(ShareLink.created_at.desc())
        .limit(1)
    )


def get_or_create_link(session: Session, project_id: str) -> ShareLink:
    link = active_link(session, project_id)
    if link is None:
        link = ShareLink(project_id=project_id, token=new_token())
        session.add(link)
        session.flush()
    return link


def options_of(link: ShareLink) -> ShareOptions:
    return ShareOptions(
        show_gantt=link.show_gantt, show_list=link.show_list, show_budget=link.show_budget
    )


def publish(
    session: Session,
    client: ShareClient,
    project_id: str,
    options: ShareOptions | None = None,
    pin: str | None = None,
    auto_update: bool | None = None,
) -> ShareLink:
    """Objavi ili ažuriraj snimak. pin=None zadržava postojeći PIN, pin="" ga uklanja."""
    link = get_or_create_link(session, project_id)
    _apply_options(link, options, pin, auto_update)
    html = render.render(snapshot.build(session, project_id, options_of(link)))
    client.publish(link.token, html, link.pin_hash)
    first = link.last_published_at is None
    link.url = client.page_url(link.token)
    link.last_published_at = datetime.now(UTC)
    activity.log(session, "share", link.id, "create" if first else "update", project_id)
    session.flush()
    return link


def _apply_options(
    link: ShareLink, options: ShareOptions | None, pin: str | None, auto_update: bool | None
) -> None:
    if options is not None:
        if not (options.show_gantt or options.show_list or options.show_budget):
            raise ValueError("Izaberi bar jedan prikaz za link (Gant, zadaci ili budžet).")
        link.show_gantt, link.show_list = options.show_gantt, options.show_list
        link.show_budget = options.show_budget
    if pin is not None:
        pin = pin.strip()
        if pin and not (4 <= len(pin) <= 32):
            raise ValueError("PIN treba da ima od 4 do 32 znaka.")
        link.pin_hash = pin_hash(link.token, pin) if pin else ""
    if auto_update is not None:
        link.auto_update = auto_update


def revoke(session: Session, client: ShareClient, link: ShareLink) -> None:
    client.revoke(link.token)
    link.revoked = True
    link.auto_update = False
    activity.log(session, "share", link.id, "delete", link.project_id)
    session.flush()


# --- lokalna mreža -------------------------------------------------------------------------------


def enable_local(
    session: Session,
    project_id: str,
    options: ShareOptions | None = None,
    pin: str | None = None,
) -> ShareLink:
    """Uključuje (ili menja) link u lokalnoj mreži. Stranica se pravi tek kad je neko otvori."""
    link = get_or_create_link(session, project_id)
    _apply_options(link, options, pin, False)
    first = link.last_published_at is None
    link.url = ""
    link.last_published_at = datetime.now(UTC)
    activity.log(session, "share", link.id, "create" if first else "update", project_id)
    session.flush()
    return link


def disable_local(session: Session, link: ShareLink) -> None:
    link.revoked = True
    link.auto_update = False
    activity.log(session, "share", link.id, "delete", link.project_id)
    session.flush()


def live_link(session: Session, token: str) -> ShareLink | None:
    """Uključen link po tokenu (za lokalni server)."""
    return session.scalar(
        select(ShareLink).where(
            ShareLink.token == token,
            ShareLink.revoked.is_(False),
            ShareLink.last_published_at.is_not(None),
        )
    )


def has_live_links(session: Session) -> bool:
    return (
        session.scalar(
            select(func.count(ShareLink.id)).where(
                ShareLink.revoked.is_(False), ShareLink.last_published_at.is_not(None)
            )
        )
        or 0
    ) > 0


def page_html(session: Session, link: ShareLink) -> str:
    return render.render(snapshot.build(session, link.project_id, options_of(link)))


def check_pin(link: ShareLink, pin: str) -> bool:
    if not link.pin_hash:
        return True
    return pysecrets.compare_digest(pin_hash(link.token, pin), link.pin_hash)


def add_local_comment(
    session: Session, link: ShareLink, author: str, text: str, task_id: str | None
) -> RemoteComment:
    """Komentar gledaoca sa lokalnog linka; greške su za prikaz gledaocu (ValueError)."""
    text = (text or "").strip()
    author = (author or "").strip()[:MAX_AUTHOR] or "Gost"
    if not text:
        raise ValueError("Komentar je prazan.")
    if len(text) > MAX_COMMENT:
        raise ValueError(f"Komentar je duži od {MAX_COMMENT} znakova.")
    count = session.scalar(
        select(func.count(RemoteComment.id)).where(RemoteComment.share_id == link.id)
    )
    if (count or 0) >= MAX_COMMENTS_PER_LINK:
        raise ValueError("Dostignut je najveći broj komentara za ovaj link.")
    if task_id:
        task = session.get(Task, task_id)
        if task is None or task.project_id != link.project_id:
            task_id = None
    comment = RemoteComment(
        share_id=link.id,
        remote_id=f"lan-{uuid.uuid4()}",
        author_name=author,
        text=text,
        task_id=task_id or None,
        posted_at=datetime.now(UTC),
    )
    session.add(comment)
    session.flush()
    return comment


def public_comments(session: Session, link: ShareLink) -> list[dict]:
    """Komentari za prikaz na stranici (bez internih polja), najstariji prvi."""
    rows = session.scalars(
        select(RemoteComment)
        .where(RemoteComment.share_id == link.id)
        .order_by(RemoteComment.posted_at)
    )
    return [
        {
            "author": c.author_name,
            "text": c.text,
            "task_id": c.task_id,
            "posted_at": c.posted_at.isoformat(),
        }
        for c in rows
    ]


# --- komentari -----------------------------------------------------------------------------------


def sync_comments(session: Session, client: ShareClient, link: ShareLink) -> int:
    """Preuzima komentare sa Worker-a i dodaje nove. Vraća broj novih."""
    remote = client.comments(link.token)
    known = set(
        session.scalars(select(RemoteComment.remote_id).where(RemoteComment.share_id == link.id))
    )
    task_ids = set(session.scalars(select(Task.id).where(Task.project_id == link.project_id)))
    added = 0
    for c in remote:
        if c.id in known:
            continue
        session.add(
            RemoteComment(
                share_id=link.id,
                remote_id=c.id,
                author_name=c.author[:120],
                text=c.text,
                task_id=c.task_id if c.task_id in task_ids else None,
                posted_at=c.posted_at,
            )
        )
        added += 1
    session.flush()
    return added


def sync_all(session: Session, client: ShareClient) -> int:
    links = session.scalars(
        select(ShareLink).where(
            ShareLink.revoked.is_(False), ShareLink.last_published_at.is_not(None)
        )
    )
    return sum(sync_comments(session, client, link) for link in links)


def comments(
    session: Session, project_id: str, task_id: str | None = None, include_resolved: bool = True
) -> list[RemoteComment]:
    stmt = (
        select(RemoteComment)
        .join(ShareLink, ShareLink.id == RemoteComment.share_id)
        .where(ShareLink.project_id == project_id)
    )
    if task_id:
        stmt = stmt.where(RemoteComment.task_id == task_id)
    if not include_resolved:
        stmt = stmt.where(RemoteComment.resolved.is_(False))
    return list(session.scalars(stmt.order_by(RemoteComment.posted_at.desc())))


def unread_count(session: Session, project_id: str) -> int:
    return int(
        session.scalar(
            select(func.count(RemoteComment.id))
            .join(ShareLink, ShareLink.id == RemoteComment.share_id)
            .where(ShareLink.project_id == project_id, RemoteComment.read.is_(False))
        )
        or 0
    )


def mark_read(session: Session, project_id: str, task_id: str | None = None) -> None:
    for c in comments(session, project_id, task_id):
        c.read = True
    session.flush()


def set_resolved(session: Session, comment: RemoteComment, resolved: bool) -> None:
    comment.resolved = resolved
    comment.read = True
    session.flush()
