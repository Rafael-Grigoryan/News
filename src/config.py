"""Configuration: environment variables and tunable constants.

Reads a local .env file if present (handy for local runs); in GitHub Actions the
values arrive as real environment variables from repo Secrets.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SEEN_FILE = DATA_DIR / "seen.json"

# --- Tunables --------------------------------------------------------------
# How many uids to retain in seen.json (oldest trimmed). Keeps the file bounded.
MAX_SEEN = 2000
# Max posts per single run, so we never hammer Telegram's rate limit.
MAX_POSTS_PER_RUN = 15
# Seconds to sleep between Telegram messages.
SEND_DELAY_SECONDS = 2.0
# Summary length cap (characters) before the "Read" link.
SUMMARY_MAX_CHARS = 400
# Telegram hard limit per message.
TELEGRAM_MAX_CHARS = 4096
# HTTP timeout (seconds) for all outbound source/Telegram requests.
HTTP_TIMEOUT = 20

USER_AGENT = (
    "anthropic-news-bot/1.0 (+https://github.com/) "
    "Mozilla/5.0 (compatible; news-aggregator)"
)


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency). Does not override real env vars."""
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


_load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- Secrets / env ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get("TELEGRAM_CHAT_ID")
NEWSAPI_KEY = _get("NEWSAPI_KEY")  # optional


class ConfigError(Exception):
    """Raised when required configuration is missing."""


def validate() -> None:
    """Ensure required secrets are present. Raises ConfigError otherwise."""
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Set them in .env (local) or repo Secrets (GitHub Actions)."
        )
