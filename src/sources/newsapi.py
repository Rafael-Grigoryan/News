"""Source 3: NewsAPI — optional extra coverage.

Requires NEWSAPI_KEY. If absent, this source silently returns []. Note the free
tier delays results (~a day) and is dev-only, so this is a backup to the
real-time Google News feed, not a primary source.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from dateutil import parser as date_parser

from .. import config
from ..models import NewsItem
from ..util import strip_html

log = logging.getLogger(__name__)

SOURCE_NAME = "NewsAPI"

ENDPOINT = "https://newsapi.org/v2/everything"
QUERY = 'Anthropic OR "Claude AI"'
PAGE_SIZE = 20


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
    except (ValueError, OverflowError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fetch() -> list[NewsItem]:
    """Return NewsItems from NewsAPI. Empty list if disabled or on failure."""
    if not config.NEWSAPI_KEY:
        log.info("[%s] no NEWSAPI_KEY set — source disabled", SOURCE_NAME)
        return []

    params = {
        "q": QUERY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": PAGE_SIZE,
        "apiKey": config.NEWSAPI_KEY,
    }

    try:
        resp = requests.get(ENDPOINT, params=params, timeout=config.HTTP_TIMEOUT)
    except requests.RequestException as exc:
        log.warning("[%s] request failed: %s", SOURCE_NAME, exc)
        return []

    if resp.status_code != 200:
        log.warning("[%s] HTTP %s: %s", SOURCE_NAME, resp.status_code, resp.text[:200])
        return []

    try:
        data = resp.json()
    except requests.JSONDecodeError as exc:
        log.warning("[%s] bad JSON: %s", SOURCE_NAME, exc)
        return []

    if data.get("status") != "ok":
        log.warning("[%s] API status %s: %s", SOURCE_NAME, data.get("status"), data.get("message"))
        return []

    items: list[NewsItem] = []
    for article in data.get("articles", []):
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        if not title or not url:
            continue
        items.append(
            NewsItem.create(
                title=title,
                url=url,
                source=SOURCE_NAME,
                published=_parse_date(article.get("publishedAt")),
                summary=strip_html(article.get("description")),
            )
        )

    log.info("[%s] fetched %d items", SOURCE_NAME, len(items))
    return items
