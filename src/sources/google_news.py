"""Source 1: Google News RSS — the primary, real-time feed."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser

from ..models import NewsItem
from ..util import strip_html

log = logging.getLogger(__name__)

SOURCE_NAME = "Google News"

# Query: Anthropic OR "Claude AI" OR "Claude Opus". Change hl/gl/ceid for another
# language/region (e.g. ru: hl=ru&gl=RU&ceid=RU:ru).
FEED_URL = (
    "https://news.google.com/rss/search"
    "?q=Anthropic+OR+%22Claude+AI%22+OR+%22Claude+Opus%22"
    "&hl=en-US&gl=US&ceid=US:en"
)


def _parse_date(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def fetch() -> list[NewsItem]:
    """Return NewsItems from the Google News RSS search. Empty list on failure."""
    items: list[NewsItem] = []
    try:
        feed = feedparser.parse(FEED_URL)
    except Exception as exc:  # feedparser is broadly tolerant, but be safe
        log.warning("[%s] feed parse failed: %s", SOURCE_NAME, exc)
        return items

    if getattr(feed, "bozo", 0) and not getattr(feed, "entries", None):
        log.warning("[%s] feed malformed and empty: %s", SOURCE_NAME, getattr(feed, "bozo_exception", ""))
        return items

    for entry in getattr(feed, "entries", []):
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        summary = strip_html(getattr(entry, "summary", ""))
        items.append(
            NewsItem.create(
                title=title,
                url=link,
                source=SOURCE_NAME,
                published=_parse_date(entry),
                summary=summary,
            )
        )

    log.info("[%s] fetched %d items", SOURCE_NAME, len(items))
    return items
