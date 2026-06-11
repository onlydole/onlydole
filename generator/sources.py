"""Fetch and parse the four content sources."""

from __future__ import annotations

import datetime
from pathlib import Path

import feedparser
import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBSTACK_FEED = "https://onlydole.substack.com/feed"
GITHUB_LOGIN = "onlydole"
PROFILE_REPO = "onlydole/onlydole"
GRAPHQL_URL = "https://api.github.com/graphql"


class SourceError(RuntimeError):
    """A content source could not be fetched or parsed."""


def parse_substack(feed_text: str) -> list[dict]:
    parsed = feedparser.parse(feed_text)
    if parsed.bozo and not parsed.entries:
        raise SourceError(f"unparseable feed: {parsed.bozo_exception}")
    posts = []
    for entry in parsed.entries[:3]:
        published = entry.get("published_parsed")
        if not (entry.get("title") and entry.get("link") and published):
            continue
        posts.append(
            {
                "title": entry["title"],
                "url": entry["link"],
                "date": datetime.date(*published[:3]).isoformat(),
            }
        )
    if not posts:
        raise SourceError("feed contained no usable entries")
    return posts


def fetch_substack() -> list[dict]:
    try:
        resp = httpx.get(SUBSTACK_FEED, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceError(f"substack fetch failed: {exc}") from exc
    return parse_substack(resp.text)
