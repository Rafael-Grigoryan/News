"""Relevance gate: keep only items genuinely about Anthropic / Claude.

The Google News and NewsAPI searches are keyword-based and loose, so they surface
a lot of off-topic noise: AI-industry roundups that merely name-drop Anthropic,
competitor coverage, articles about people/places named "Claude", etc. This module
decides whether an item is actually *about* Anthropic or its products, so the
channel stays on-topic.

Heuristic (tuned to drop tangential mentions, not just any mention):
  * Items from a trusted first-party source (the official newsroom) are always kept.
  * Otherwise the *title* must carry an unambiguous Anthropic/Claude product term,
    because a roundup that only name-drops Anthropic in the body rarely puts it in
    the headline. A bare "Claude" in the title counts only when AI context co-occurs
    (in title or summary), so a "Claude Monet" headline doesn't slip through.
"""

from __future__ import annotations

import re

from .models import NewsItem

# Sources whose every item is first-party and therefore always on-topic.
TRUSTED_SOURCES = {"Anthropic"}

# Unambiguous Anthropic / Claude product terms. Any one in the title → relevant.
STRONG_TERMS = (
    "anthropic",
    "claude ai",
    "claude.ai",
    "claude code",
    "claude opus",
    "claude sonnet",
    "claude haiku",
    "claude model",
    "claude 2",
    "claude 3",
    "claude 4",
)

# A bare "claude" is ambiguous (Claude Monet, Claude Shannon, people named Claude),
# so it only counts when genuine AI context appears alongside it.
_CLAUDE_RE = re.compile(r"\bclaude\b", re.IGNORECASE)
_AI_CONTEXT_RE = re.compile(
    r"\b(?:anthropic|ai|llm|model|chatbot|assistant|opus|sonnet|haiku|"
    r"openai|chatgpt|gpt|gemini|copilot|agent|api|token|generative|"
    r"artificial intelligence|machine learning|neural)\b",
    re.IGNORECASE,
)


def is_relevant(item: NewsItem) -> bool:
    """True if the item is actually about Anthropic / Claude, not a tangential mention."""
    if item.source in TRUSTED_SOURCES:
        return True

    title = (item.title or "").lower()

    # Primary signal: an unambiguous Anthropic/Claude product term in the headline.
    if any(term in title for term in STRONG_TERMS):
        return True

    # Bare "Claude" in the title: accept only with AI context (title or summary).
    if _CLAUDE_RE.search(title):
        context = title + " " + (item.summary or "").lower()
        if _AI_CONTEXT_RE.search(context):
            return True

    return False