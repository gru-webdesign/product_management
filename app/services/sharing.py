"""Deljenje projekta linkom: objava snimka, opoziv, komentari gledalaca."""

from __future__ import annotations

import hashlib
import secrets as pysecrets
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
    html = render.render(snapshot.build(session, project_id, options_of(link)))
    client.publish(link.token, html, link.pin_hash)
    first = link.last_published_at is None
    link.url = client.page_url(link.token)
    link.last_published_at = datetime.now(UTC)
    activity.log(session, "share", link.id, "create" if first else "update", project_id)
    session.flush()
    return link


def revoke(session: Session, client: ShareClient, link: ShareLink) -> None:
    client.revoke(link.token)
    link.revoked = True
    link.auto_update = False
    activity.log(session, "share", link.id, "delete", link.project_id)
    session.flush()


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
