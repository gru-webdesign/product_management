"""Tajni ključ Worker-a čuva se u sistemskom skladištu lozinki (Windows Credential Manager).

Ako sistemsko skladište nije dostupno, ključ se čuva u lokalnoj bazi (uz upozorenje u
podešavanjima), da deljenje i dalje radi.
"""

from __future__ import annotations

import keyring
from keyring.errors import KeyringError
from sqlalchemy.orm import Session

from app import APP_NAME
from app.services.defaults import get_setting, set_setting

USERNAME = "share_worker_admin_key"
FALLBACK_SETTING = "share_admin_key_fallback"


def get_admin_key(session: Session) -> str:
    try:
        value = keyring.get_password(APP_NAME, USERNAME)
        if value:
            return value
    except KeyringError:
        pass
    return get_setting(session, FALLBACK_SETTING)


def set_admin_key(session: Session, value: str) -> bool:
    """Vraća True ako je ključ u sistemskom skladištu, False ako je pao na lokalnu bazu."""
    value = value.strip()
    try:
        if value:
            keyring.set_password(APP_NAME, USERNAME, value)
        else:
            try:
                keyring.delete_password(APP_NAME, USERNAME)
            except KeyringError:
                pass
        set_setting(session, FALLBACK_SETTING, "")
        return True
    except KeyringError:
        set_setting(session, FALLBACK_SETTING, value)
        return False


def uses_fallback(session: Session) -> bool:
    return bool(get_setting(session, FALLBACK_SETTING))
