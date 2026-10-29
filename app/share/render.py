"""Snimak projekta → jedan samostalan HTML fajl (bez spoljnih fontova, skripti i slika)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(snapshot: dict) -> str:
    """`tojson` u šablonu escapuje <, >, & i ', pa podaci ne mogu da zatvore <script> tag."""
    return _env.get_template("share.html").render(data=snapshot)
