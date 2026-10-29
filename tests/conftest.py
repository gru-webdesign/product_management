from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from app.config import get_paths  # noqa: E402
from app.main import bootstrap  # noqa: E402


class _MemoryKeyring:
    """Zamena za sistemsko skladište lozinki u testovima."""

    priority = 1

    def __init__(self):
        self.data = {}

    def get_password(self, service, user):
        return self.data.get((service, user))

    def set_password(self, service, user, value):
        self.data[(service, user)] = value

    def delete_password(self, service, user):
        self.data.pop((service, user), None)


@pytest.fixture(autouse=True)
def _memory_keyring(monkeypatch):
    import keyring

    ring = _MemoryKeyring()
    monkeypatch.setattr(keyring, "get_password", ring.get_password)
    monkeypatch.setattr(keyring, "set_password", ring.set_password)
    monkeypatch.setattr(keyring, "delete_password", ring.delete_password)
    return ring


@pytest.fixture(autouse=True, scope="session")
def _serbian_locale():
    from app.main import set_locale

    set_locale()


@pytest.fixture
def paths(tmp_path):
    return get_paths(tmp_path / "data").ensure()


@pytest.fixture
def db(paths):
    database = bootstrap(paths)
    yield database
    database.dispose()


@pytest.fixture
def session(db):
    with db.session() as s:
        yield s
