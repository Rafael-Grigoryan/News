"""Persistent dedup state stored in data/seen.json.

Format: {"seen": ["uid1", "uid2", ...]}. The list is ordered oldest -> newest so
trimming drops the oldest uids first.
"""

from __future__ import annotations

import json
import logging

from . import config

log = logging.getLogger(__name__)


def load_seen() -> list[str]:
    """Return the seen uids as an ordered list (oldest first).

    Missing or malformed files are treated as an empty state rather than fatal —
    a corrupt state should not stop the bot from running.
    """
    path = config.SEEN_FILE
    if not path.exists():
        log.info("seen.json not found at %s — treating as first run", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read seen.json (%s) — treating as empty", exc)
        return []

    seen = data.get("seen") if isinstance(data, dict) else None
    if not isinstance(seen, list):
        log.warning("seen.json has unexpected shape — treating as empty")
        return []
    # Keep only strings, drop dupes while preserving order.
    out: list[str] = []
    seen_set: set[str] = set()
    for uid in seen:
        if isinstance(uid, str) and uid not in seen_set:
            seen_set.add(uid)
            out.append(uid)
    return out


def save_seen(seen: list[str]) -> None:
    """Persist seen uids, trimming to the newest MAX_SEEN entries."""
    trimmed = seen[-config.MAX_SEEN :]
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"seen": trimmed}, ensure_ascii=False, indent=2)
    config.SEEN_FILE.write_text(payload + "\n", encoding="utf-8")
    log.info("Saved seen.json (%d uids)", len(trimmed))
