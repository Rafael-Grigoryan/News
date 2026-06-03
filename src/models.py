"""Normalized news item shared by all sources."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters used purely for tracking; stripped when building a uid so the
# same article reached via different campaigns collapses to one entry.
_TRACKING_PREFIXES = ("utm_", "ga_", "fbclid", "gclid", "mc_", "_hs")
_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "yclid",
    "igshid",
    "ref",
    "ref_src",
    "source",
    "cmpid",
    "spm",
}


def _is_tracking_param(key: str) -> bool:
    key_l = key.lower()
    if key_l in _TRACKING_KEYS:
        return True
    return any(key_l.startswith(prefix) for prefix in _TRACKING_PREFIXES)


def normalize_url(url: str) -> str:
    """Lowercase host, drop tracking query params, strip fragments and trailing slash.

    Used to build a stable deduplication key. Falls back to returning the input
    unchanged if parsing fails for any reason.
    """
    try:
        parts = urlsplit(url.strip())
    except (ValueError, AttributeError):
        return url.strip()

    if not parts.netloc:
        return url.strip()

    host = parts.netloc.lower()
    # Drop a leading "www." so www / bare host collapse together.
    if host.startswith("www."):
        host = host[4:]

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if not _is_tracking_param(k)]
    kept.sort()
    query = urlencode(kept)

    path = parts.path.rstrip("/") or "/"

    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))


def make_uid(title: str, url: str) -> str:
    """Build a deduplication key.

    Prefer the normalized URL (human-readable, stable). If the URL is missing or
    obviously unusable, hash title+url so we still get a deterministic key.
    """
    normalized = normalize_url(url) if url else ""
    if normalized and normalized.startswith(("http://", "https://")):
        return normalized
    raw = f"{title}\n{url}".encode("utf-8", "ignore")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass
class NewsItem:
    """A single news entry normalized across all sources."""

    uid: str
    title: str
    url: str
    source: str
    published: datetime | None = None
    summary: str | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        url: str,
        source: str,
        published: datetime | None = None,
        summary: str | None = None,
    ) -> "NewsItem":
        """Build a NewsItem, computing the uid from title+url."""
        title = (title or "").strip()
        url = (url or "").strip()
        return cls(
            uid=make_uid(title, url),
            title=title,
            url=url,
            source=source,
            published=published,
            summary=(summary or "").strip() or None,
        )
