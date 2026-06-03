"""Small shared text helpers."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")


def strip_html(text: str | None) -> str | None:
    """Remove HTML tags/entities and collapse whitespace. Returns None if empty."""
    if not text:
        return None
    try:
        cleaned = BeautifulSoup(text, "html.parser").get_text(separator=" ")
    except Exception:
        cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = _WS.sub(" ", cleaned).strip()
    return cleaned or None
