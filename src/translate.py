"""Translate news items to Russian just before posting.

Uses deep-translator's free Google Translate backend (no API key). Best-effort:
any failure — import error, network blip, rate limit, empty result — falls back
to the original text, mirroring how sources swallow their own errors. The run
never breaks because of translation, and a post is always sent (worst case in
the original language).

Only the items actually being posted are translated (≤ MAX_POSTS_PER_RUN), so
the number of network calls stays small and predictable.
"""

from __future__ import annotations

import logging

from .models import NewsItem

log = logging.getLogger(__name__)

TARGET_LANG = "ru"
# Google Translate's free endpoint rejects very long inputs; stay well within bounds.
_MAX_CHARS = 4500

# In-process cache: identical strings within a single run aren't re-translated.
_cache: dict[str, str] = {}


def _looks_russian(text: str) -> bool:
    """True if the text is already predominantly Cyrillic — no need to translate it."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    cyrillic = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    return cyrillic / len(letters) > 0.5


def translate(text: str | None) -> str | None:
    """Translate `text` to Russian, best-effort. Returns the original on any failure."""
    if not text or not text.strip():
        return text
    if _looks_russian(text):
        return text
    if text in _cache:
        return _cache[text]

    try:
        from deep_translator import GoogleTranslator

        result = GoogleTranslator(source="auto", target=TARGET_LANG).translate(text[:_MAX_CHARS])
    except Exception as exc:  # import/network/rate-limit — never fatal
        log.warning("translation failed (%s); keeping original text", exc)
        return text

    if not result or not result.strip():
        return text
    _cache[text] = result
    return result


def translate_item(item: NewsItem) -> NewsItem:
    """Translate an item's title and summary to Russian in place, then return it.

    Safe to call after dedup/seen-filtering: the uid is URL-based and independent
    of the (now translated) title, so state tracking is unaffected.
    """
    item.title = translate(item.title) or item.title
    item.summary = translate(item.summary)
    return item
