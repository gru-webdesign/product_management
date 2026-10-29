from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from app.config import get_paths  # noqa: E402
from app.main import bootstrap  # noqa: E402


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
