"""Klijent za Etapa Cloudflare Worker (objava snimka, opoziv, preuzimanje komentara)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import httpx

TIMEOUT = httpx.Timeout(15.0, connect=8.0)


class ShareError(Exception):
    """Greška sa porukom za korisnika (na srpskom)."""


@dataclass
class RemoteCommentData:
    id: str
    author: str
    text: str
    task_id: str | None
    posted_at: datetime


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ShareError("Adresa Worker-a mora počinjati sa https://")
    if not parsed.hostname:
        raise ShareError("Adresa Worker-a nije ispravna.")
    return url


class ShareClient:
    def __init__(
        self, base_url: str, admin_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.base_url = normalize_url(base_url)
        if not admin_key or len(admin_key) < 16:
            raise ShareError("Tajni ključ Worker-a nije podešen (najmanje 16 znakova).")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"authorization": f"Bearer {admin_key}", "user-agent": "Etapa"},
            timeout=TIMEOUT,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ShareClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def page_url(self, token: str) -> str:
        return f"{self.base_url}/p/{token}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ShareError("Worker ne odgovara (isteklo vreme). Proveri internet vezu.") from exc
        except httpx.HTTPError as exc:
            raise ShareError(
                f"Nema veze sa Worker-om: {exc.__class__.__name__}. Proveri adresu i internet vezu."
            ) from exc
        if response.status_code == 401:
            raise ShareError("Worker je odbio tajni ključ. Proveri ključ u podešavanjima.")
        if response.status_code == 404 and path.endswith("/ping"):
            raise ShareError("Na ovoj adresi nije Etapa Worker.")
        try:
            data = response.json()
        except ValueError as exc:
            raise ShareError(f"Neočekivan odgovor Worker-a (HTTP {response.status_code}).") from exc
        if response.status_code >= 400:
            raise ShareError(data.get("error") or f"Greška Worker-a (HTTP {response.status_code}).")
        return data

    def ping(self) -> str:
        data = self._request("GET", "/api/admin/ping")
        return str(data.get("version", ""))

    def publish(self, token: str, html: str, pin_hash: str = "") -> None:
        self._request(
            "PUT", f"/api/admin/snapshots/{token}", json={"html": html, "pin_hash": pin_hash}
        )

    def revoke(self, token: str) -> None:
        self._request("DELETE", f"/api/admin/snapshots/{token}")

    def comments(self, token: str) -> list[RemoteCommentData]:
        data = self._request("GET", f"/api/admin/comments/{token}")
        out = []
        for c in data.get("comments", []):
            try:
                posted = datetime.fromisoformat(str(c["posted_at"]).replace("Z", "+00:00"))
                out.append(
                    RemoteCommentData(
                        str(c["id"]),
                        str(c.get("author") or "Gost"),
                        str(c.get("text") or ""),
                        c.get("task_id"),
                        posted,
                    )
                )
            except (KeyError, ValueError):
                continue
        return out
