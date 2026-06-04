"""Orchestrator: gather news, dedupe, post new items to Telegram, persist state.

Run with:  python -m src.main

Exit codes:
  0 — normal run (even if some sources failed; that's expected and tolerated).
  2 — fatal configuration error (missing required secrets).
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone

from . import config, state, telegram, translate
from .models import NewsItem
from .sources import anthropic_news, google_news, newsapi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("anthropic_news_bot")

# Source modules in priority order. Each must expose fetch() -> list[NewsItem].
SOURCES = (google_news, anthropic_news, newsapi)


def gather() -> list[NewsItem]:
    """Fetch from every source, isolating failures so one bad source can't sink the run."""
    collected: list[NewsItem] = []
    for module in SOURCES:
        name = getattr(module, "SOURCE_NAME", module.__name__)
        try:
            collected.extend(module.fetch())
        except Exception as exc:  # defensive: sources catch their own errors, but be safe
            log.warning("source %s crashed: %s", name, exc)
    return collected


def dedupe(items: list[NewsItem]) -> list[NewsItem]:
    """Drop duplicate uids within this batch, keeping first occurrence."""
    out: list[NewsItem] = []
    seen: set[str] = set()
    for item in items:
        if item.uid in seen:
            continue
        seen.add(item.uid)
        out.append(item)
    return out


def _sort_key(item: NewsItem):
    """Chronological sort key; undated items sort oldest (epoch) so they post first."""
    return item.published or datetime.min.replace(tzinfo=timezone.utc)


def run() -> int:
    try:
        config.validate()
    except config.ConfigError as exc:
        log.error("%s", exc)
        return 2

    seen_list = state.load_seen()
    seen_set = set(seen_list)
    first_run = len(seen_set) == 0

    raw = gather()
    batch = dedupe(raw)
    fresh = [item for item in batch if item.uid not in seen_set]
    fresh.sort(key=_sort_key)

    log.info(
        "summary: fetched=%d unique=%d new=%d (first_run=%s)",
        len(raw),
        len(batch),
        len(fresh),
        first_run,
    )

    # --- Seed mode (anti-flood) -------------------------------------------
    # On the very first run we record everything as seen WITHOUT posting, so we
    # don't dump dozens of historical articles into the channel at once.
    if first_run:
        seed_uids = [item.uid for item in batch]
        state.save_seen(seen_list + seed_uids)
        log.info("first run: seeded %d uids without posting", len(seed_uids))
        return 0

    if not fresh:
        log.info("nothing new to post")
        # Still persist (no-op content-wise) to keep the file tidy/canonical.
        state.save_seen(seen_list)
        return 0

    # --- Post new items ----------------------------------------------------
    to_post = fresh[: config.MAX_POSTS_PER_RUN]
    if len(fresh) > len(to_post):
        log.info(
            "%d new items; posting %d this run, %d deferred to next run",
            len(fresh),
            len(to_post),
            len(fresh) - len(to_post),
        )

    posted = 0
    errors = 0
    for idx, item in enumerate(to_post):
        translate.translate_item(item)  # to Russian; falls back to original on failure
        if telegram.send_message(item):
            seen_list.append(item.uid)
            seen_set.add(item.uid)
            posted += 1
            log.info("posted: %s", item.title[:80])
        else:
            errors += 1
            log.warning("failed to post: %s", item.title[:80])
        # Throttle between messages (not after the last one).
        if idx < len(to_post) - 1:
            time.sleep(config.SEND_DELAY_SECONDS)

    state.save_seen(seen_list)
    log.info("done: posted=%d errors=%d", posted, errors)
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
