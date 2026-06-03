"""Telegram channel posting via the Bot API."""

from __future__ import annotations

import html
import logging
import time

import requests

from . import config
from .models import NewsItem

log = logging.getLogger(__name__)


def _api_url() -> str:
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"


def _truncate(text: str, limit: int) -> str:
    """Trim to `limit` chars on a word boundary, adding an ellipsis."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    # Avoid slicing mid-word when there's a nearby space.
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip() + "…"


def format_message(item: NewsItem) -> str:
    """Render a NewsItem as an HTML Telegram message (escaped, length-bounded)."""
    title = html.escape(item.title or "(no title)")
    parts = [f"<b>{title}</b>"]

    if item.summary:
        summary = _truncate(item.summary, config.SUMMARY_MAX_CHARS)
        parts.append("")
        parts.append(html.escape(summary))

    parts.append("")
    parts.append(f"📰 {html.escape(item.source)}")
    url = html.escape(item.url, quote=True)
    parts.append(f'🔗 <a href="{url}">Читать</a>')

    message = "\n".join(parts)
    # Hard cap at Telegram's per-message limit.
    if len(message) > config.TELEGRAM_MAX_CHARS:
        message = message[: config.TELEGRAM_MAX_CHARS - 1] + "…"
    return message


def send_text(text: str, *, disable_preview: bool = False) -> bool:
    """Send a raw HTML message. Returns True on success.

    Handles HTTP 429 by honoring `retry_after` and retrying once.
    """
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }

    for attempt in (1, 2):
        try:
            resp = requests.post(_api_url(), data=payload, timeout=config.HTTP_TIMEOUT)
        except requests.RequestException as exc:
            log.warning("Telegram request failed: %s", exc)
            return False

        if resp.status_code == 200:
            return True

        if resp.status_code == 429 and attempt == 1:
            retry_after = 5
            try:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
            except (ValueError, KeyError, requests.JSONDecodeError):
                pass
            log.warning("Rate limited by Telegram; waiting %ss", retry_after)
            time.sleep(retry_after + 1)
            continue

        # Other errors: log body for debugging and give up on this message.
        log.warning("Telegram error %s: %s", resp.status_code, resp.text[:300])
        return False

    return False


def send_message(item: NewsItem) -> bool:
    """Post a single news item to the channel. Link preview enabled."""
    return send_text(format_message(item), disable_preview=False)
