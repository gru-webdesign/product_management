"""Provera nove verzije preko GitHub izdanja (releases). Samo čita, ništa ne preuzima."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app import __version__

REPO = "gru-webdesign/product_management"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"


@dataclass(frozen=True)
class UpdateInfo:
    latest: str
    url: str
    notes: str

    @property
    def newer(self) -> bool:
        return parse_version(self.latest) > parse_version(__version__)


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.0' → (1, 2, 0); delovi koji nisu brojevi se zanemaruju."""
    nums = re.findall(r"\d+", text.split("-")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


def _safe_url(url) -> str:
    """Otvara se samo stranica ovog projekta na GitHub-u, nikad proizvoljna adresa iz odgovora."""
    url = str(url or "")
    return url if url.startswith(RELEASES_URL.rsplit("/releases", 1)[0] + "/") else RELEASES_URL


def check(client: httpx.Client | None = None, timeout: float = 8.0) -> UpdateInfo | None:
    """Poslednje izdanje ili None ako izdanja još nema. Mrežne greške se prosleđuju."""
    own = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        r = client.get(API_URL, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
    finally:
        if own:
            client.close()
    return UpdateInfo(
        latest=str(data.get("tag_name") or data.get("name") or "0"),
        url=_safe_url(data.get("html_url")),
        notes=str(data.get("body") or "").strip(),
    )
