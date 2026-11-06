from __future__ import annotations

import httpx

from app import __version__
from app.services import updates


def _client(status: int, payload: dict | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/releases/latest")
        return httpx.Response(status, json=payload or {})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_version():
    assert updates.parse_version("v1.2.0") == (1, 2, 0)
    assert updates.parse_version("1.10") > updates.parse_version("1.9.9")
    assert updates.parse_version("v2.0.0-beta") == (2, 0, 0)


def test_check_newer_and_same():
    url = updates.RELEASES_URL + "/tag/v99.0.0"
    info = updates.check(_client(200, {"tag_name": "v99.0.0", "html_url": url}))
    assert info.newer and info.url == url
    same = updates.check(_client(200, {"tag_name": f"v{__version__}"}))
    assert not same.newer


def test_check_no_releases():
    assert updates.check(_client(404)) is None


def test_update_link_is_always_this_repository():
    from app.services import updates

    assert updates._safe_url("https://evil.example/x") == updates.RELEASES_URL
    ok = updates.RELEASES_URL + "/tag/v9.0.0"
    assert updates._safe_url(ok) == ok
