# Anthropic News Bot

A zero-server Telegram bot that auto-posts fresh news about **Anthropic** and its
products (Claude, etc.) to a Telegram channel.

It runs on a schedule via **GitHub Actions** (free): every ~30 minutes a Python
script wakes up, checks the sources, posts anything new, commits its state file,
and exits. No always-on server, no database.

## How it works

```
Google News RSS ─┐
Anthropic /news  ├─▶  normalize ─▶ dedupe vs data/seen.json ─▶ post new to Telegram ─▶ commit seen.json
NewsAPI (opt.)  ─┘
```

- **Sources** (`src/sources/`): each exposes `fetch() -> list[NewsItem]` and
  swallows its own network/parse errors, so one broken source never sinks the run.
  - `google_news.py` — Google News RSS search. **Primary, real-time** source.
  - `anthropic_news.py` — official newsroom. Tries RSS/Atom first, falls back to
    scraping `https://www.anthropic.com/news`.
  - `newsapi.py` — optional extra coverage; disabled unless `NEWSAPI_KEY` is set.
    (Free tier is delayed ~a day and dev-only — a backup, not the main feed.)
- **State** (`data/seen.json`): the set of already-posted item uids, capped at the
  newest 2000. Committed back to the repo each run.
- **Anti-flood seed mode**: on the *first* run (empty `seen.json`) the bot records
  all current items as "seen" **without posting**, so it doesn't dump dozens of
  historical articles at once. From the next run on, only genuinely new items post.

## Manual setup (done once, by a human — not in code)

These steps are not automated. Do them yourself:

1. **Create the bot** via [@BotFather](https://t.me/BotFather) → copy the
   `TELEGRAM_BOT_TOKEN`.
2. **Create a Telegram channel** and add the bot as an **administrator** with
   permission to post messages.
3. **Find the channel `chat_id`:**
   - Public channel → just use `@your_channel_username`.
   - Private channel → numeric `-100…`. Easiest ways: forward a channel post to
     [@userinfobot](https://t.me/userinfobot), or temporarily call
     `https://api.telegram.org/bot<TOKEN>/getUpdates` after posting in the channel
     and read `chat.id`.
4. *(Optional)* Register a key at [newsapi.org](https://newsapi.org) → `NEWSAPI_KEY`.
5. In the GitHub repo: **Settings → Secrets and variables → Actions** → add:
   - `TELEGRAM_BOT_TOKEN` (required)
   - `TELEGRAM_CHAT_ID` (required)
   - `NEWSAPI_KEY` (optional — leave unset to skip that source)

That's it. The workflow in `.github/workflows/news.yml` runs on its own from then on.
You can also trigger it manually: **Actions → Anthropic News Bot → Run workflow**.

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in the values
python -m src.main
```

- The **first local run** is seed mode: it fills `data/seen.json` and posts nothing.
- Run it again after a new article appears to see a real post.
- `src/config.py` holds the tunables (`MAX_POSTS_PER_RUN`, `SUMMARY_MAX_CHARS`,
  `SEND_DELAY_SECONDS`, etc.). The Google News feed language/region lives in
  `src/sources/google_news.py` (`hl`/`gl`/`ceid` — e.g. switch to `ru`).

## Message format

```
<b>{title}</b>

{summary, trimmed to ~400 chars}

📰 {source}
🔗 Читать → {url}
```

HTML parse mode, special chars escaped, capped at Telegram's 4096-char limit, link
preview on. At most 15 posts per run (the rest carry over), with a 2s gap between
messages and `retry_after` handling on HTTP 429.

## Operational notes

- **Scheduled workflows auto-disable after 60 days of repo inactivity.** The bot's
  own `seen.json` commits usually count as activity, but if it goes quiet: open the
  repo, hit **Enable workflow** (or push any commit) to wake it back up.
- GitHub Actions is **free with no minute cap for public repos**; private repos have
  a free monthly quota that's normally plenty for a 30-minute cadence.
- GitHub may delay `schedule` runs by a few minutes under load — normal; a 30-minute
  interval is robust to it.
- **If the Anthropic source stops parsing** (site re-design), only the selectors in
  `src/sources/anthropic_news.py` need fixing — they're all constants at the top of
  the file, and the run logs a clear warning when zero articles are found.
- The script exits `0` even if some sources fail (so the workflow stays green). It
  exits non-zero only on a fatal config error (missing required secrets).

## Project layout

```
.
├── .github/workflows/news.yml   # scheduler + manual trigger
├── src/
│   ├── main.py                  # orchestrator
│   ├── config.py                # env vars + constants
│   ├── models.py                # NewsItem + uid normalization
│   ├── state.py                 # load/save seen.json
│   ├── telegram.py              # channel posting
│   ├── util.py                  # html-stripping helper
│   └── sources/
│       ├── google_news.py
│       ├── anthropic_news.py
│       └── newsapi.py
├── data/seen.json               # state ({"seen": []})
├── requirements.txt
└── .env.example
```

## Possible future improvements (not in this MVP)

- Translate titles/summaries to Russian/Armenian before posting.
- Noise filter: drop items whose title lacks "Anthropic"/"Claude".
- Category tags (products / business / research) with emoji.
- A second mirror channel in another language.
