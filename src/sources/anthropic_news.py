"""Source 2: official Anthropic newsroom — first-party announcements.

Strategy:
  1. Try known RSS/Atom feed URLs.
  2. Try to discover a feed via <link rel="alternate"> on the news page.
  3. Fall back to scraping article cards out of the /news HTML.

NOTE for maintainers: the site's markup changes over time. All CSS selectors and
candidate URLs live in the constants below — adjust them here if scraping breaks.
A clear warning is logged when zero articles are found.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .. import config
from ..models import NewsItem
from ..util import strip_html

log = logging.getLogger(__name__)

SOURCE_NAME = "Anthropic"

BASE_URL = "https://www.anthropic.com"
NEWS_URL = "https://www.anthropic.com/news"

# Candidate feed URLs, tried in order.
FEED_CANDIDATES = (
    "https://www.anthropic.com/rss.xml",
    "https://www.anthropic.com/news/rss",
    "https://www.anthropic.com/feed.xml",
)

# Selectors for the HTML fallback. The site is link-heavy, so we primarily look
# for anchors pointing at /news/<slug> and treat their text as the title.
ARTICLE_LINK_SELECTOR = 'a[href^="/news/"], a[href^="https://www.anthropic.com/news/"]'
# Within a card the title lives either in a heading (featured cards) or an element
# whose class contains "title" (regular list cards).
TITLE_SELECTOR = 'h1, h2, h3, h4, [class*="title" i]'
# Paths under /news that are listing/index pages, not articles — skip them.
NON_ARTICLE_PATHS = {"/news", "/news/"}

_HEADERS = {"User-Agent": config.USER_AGENT}


def _extract_title(anchor) -> str:
    """Pull a clean title from a card anchor.

    Featured cards use an <h2>; regular list cards use a <span class="...title">.
    As a last resort use the anchor's text with the meta block (date/category)
    removed, so the date doesn't leak into the title.
    """
    el = anchor.select_one(TITLE_SELECTOR)
    if el:
        text = el.get_text(separator=" ", strip=True)
        if text:
            return text

    # Fallback: full anchor text minus any <time> / meta elements.
    clone = anchor
    parts = []
    for child in clone.find_all(string=True):
        parent = child.parent
        cls = " ".join(parent.get("class", [])) if parent and parent.has_attr("class") else ""
        if parent and (parent.name == "time" or "meta" in cls or "date" in cls or "subject" in cls):
            continue
        s = child.strip()
        if s:
            parts.append(s)
    return " ".join(parts).strip()


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


def _from_feed(feed_url: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    feed = feedparser.parse(feed_url)
    entries = getattr(feed, "entries", [])
    if not entries:
        return items
    for entry in entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        published = getattr(entry, "published", None) or getattr(entry, "updated", None)
        items.append(
            NewsItem.create(
                title=title,
                url=urljoin(BASE_URL, link),
                source=SOURCE_NAME,
                published=_parse_date(published),
                summary=strip_html(getattr(entry, "summary", "")),
            )
        )
    return items


def _discover_feed_url(soup: BeautifulSoup) -> str | None:
    link = soup.find("link", rel=lambda v: v and "alternate" in v, type="application/rss+xml")
    if not link:
        link = soup.find("link", type="application/atom+xml")
    if link and link.get("href"):
        return urljoin(BASE_URL, link["href"])
    return None


def _scrape_html(html: str) -> list[NewsItem]:
    soup = BeautifulSoup(html, "html.parser")

    # If the page advertises a feed, prefer that over scraping.
    discovered = _discover_feed_url(soup)
    if discovered:
        log.info("[%s] discovered feed via <link>: %s", SOURCE_NAME, discovered)
        feed_items = _from_feed(discovered)
        if feed_items:
            return feed_items

    items: list[NewsItem] = []
    seen_paths: set[str] = set()

    for anchor in soup.select(ARTICLE_LINK_SELECTOR):
        href = anchor.get("href", "").strip()
        if not href:
            continue
        url = urljoin(BASE_URL, href)
        path = urlsplit(url).path
        if path in NON_ARTICLE_PATHS or path in seen_paths:
            continue

        title = _extract_title(anchor)
        if not title or len(title) < 4:
            continue

        # Date from a nearby <time> element (datetime attr preferred).
        published = None
        time_el = anchor.find("time") or (anchor.parent.find("time") if anchor.parent else None)
        if time_el:
            published = _parse_date(time_el.get("datetime") or time_el.get_text(strip=True))

        # Summary from the card's body paragraph, if present.
        summary = None
        body = anchor.find("p")
        if body:
            summary = strip_html(body.get_text(separator=" ", strip=True))

        seen_paths.add(path)
        items.append(
            NewsItem.create(
                title=title,
                url=url,
                source=SOURCE_NAME,
                published=published,
                summary=summary,
            )
        )

    return items


def fetch() -> list[NewsItem]:
    """Return NewsItems from the Anthropic newsroom. Empty list on failure."""
    # 1) Try known feed URLs first.
    for feed_url in FEED_CANDIDATES:
        try:
            items = _from_feed(feed_url)
        except Exception as exc:
            log.debug("[%s] feed %s failed: %s", SOURCE_NAME, feed_url, exc)
            continue
        if items:
            log.info("[%s] fetched %d items from feed %s", SOURCE_NAME, len(items), feed_url)
            return items

    # 2 & 3) Fetch the news page; discover feed or scrape cards.
    try:
        resp = requests.get(NEWS_URL, headers=_HEADERS, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("[%s] could not load %s: %s", SOURCE_NAME, NEWS_URL, exc)
        return []

    try:
        items = _scrape_html(resp.text)
    except Exception as exc:
        log.warning("[%s] HTML parse failed: %s", SOURCE_NAME, exc)
        return []

    if not items:
        log.warning(
            "[%s] no articles found — site markup may have changed; "
            "check selectors in src/sources/anthropic_news.py",
            SOURCE_NAME,
        )
    else:
        log.info("[%s] scraped %d items from %s", SOURCE_NAME, len(items), NEWS_URL)
    return items
