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


def _entry_date(published) -> str | None:
    """ISO date from a feedparser struct_time, or None if absent/invalid."""
    try:
        return datetime.date(*published[:3]).isoformat()
    except (TypeError, ValueError):
        return None


def parse_substack(feed_text: str) -> list[dict]:
    parsed = feedparser.parse(feed_text)
    if parsed.bozo and not parsed.entries:
        raise SourceError(f"unparsable feed: {parsed.bozo_exception}")
    posts = []
    for entry in parsed.entries[:3]:
        date = _entry_date(entry.get("published_parsed"))
        if not (entry.get("title") and entry.get("link") and date):
            continue
        posts.append(
            {
                "title": entry["title"],
                "url": entry["link"],
                "date": date,
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


ACTIVITY_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 50, privacy: PUBLIC, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        url
        releases(first: 3, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { tagName publishedAt url }
        }
      }
    }
    pullRequests(first: 20, states: MERGED,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        title
        url
        mergedAt
        repository { nameWithOwner isPrivate }
      }
    }
  }
}
"""


def parse_activity(payload: dict) -> list[dict]:
    try:
        user = payload["data"]["user"]
        repo_nodes = user["repositories"]["nodes"]
        pr_nodes = user["pullRequests"]["nodes"]
    except (KeyError, TypeError) as exc:
        raise SourceError(f"unexpected GraphQL shape: {exc}") from exc
    items = []
    for repo in repo_nodes:
        for release in repo["releases"]["nodes"]:
            if not release.get("publishedAt"):
                continue
            items.append(
                {
                    "title": f"{repo['name']} {release['tagName']}",
                    "detail": "release",
                    "url": release["url"],
                    "date": release["publishedAt"][:10],
                }
            )
    for pr in pr_nodes:
        repo = pr["repository"]  # null when the repository was deleted
        if not repo or repo["isPrivate"] or repo["nameWithOwner"] == PROFILE_REPO:
            continue
        if not pr.get("mergedAt"):
            continue
        items.append(
            {
                "title": pr["title"],
                "detail": f"merged · {repo['nameWithOwner']}",
                "url": pr["url"],
                "date": pr["mergedAt"][:10],
            }
        )
    if not items:
        raise SourceError("no public activity found")
    items.sort(key=lambda item: item["date"], reverse=True)
    return items[:3]


def fetch_activity(token: str) -> list[dict]:
    try:
        resp = httpx.post(
            GRAPHQL_URL,
            json={"query": ACTIVITY_QUERY, "variables": {"login": GITHUB_LOGIN}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceError(f"github fetch failed: {exc}") from exc
    payload = resp.json()
    if payload.get("errors"):
        raise SourceError(f"graphql errors: {payload['errors']}")
    return parse_activity(payload)


def load_talks(path: Path | None = None) -> list[dict]:
    path = path or REPO_ROOT / "data" / "talks.yaml"
    entries = _load_yaml(path)
    if not isinstance(entries, list) or not entries:
        raise SourceError("talks.yaml must be a non-empty list")
    for entry in entries:
        for field in ("title", "venue", "date", "url"):
            if not entry.get(field):
                raise SourceError(f"talks.yaml entry missing {field!r}")
    entries.sort(key=lambda e: str(e["date"]), reverse=True)
    return [
        {
            "title": e["title"],
            "venue": e["venue"],
            "date": str(e["date"]),
            "url": e["url"],
            "kind": e.get("kind", "talk"),
        }
        for e in entries[:3]
    ]


def load_reading(path: Path | None = None) -> dict:
    path = path or REPO_ROOT / "data" / "reading.yaml"
    data = _load_yaml(path)
    current = (data or {}).get("current") or {}
    if not (current.get("title") and current.get("author")):
        raise SourceError("reading.yaml needs current.title and current.author")
    return {
        "title": current["title"],
        "author": current["author"],
        "url": current.get("url") or "",
        "note": current.get("note") or "",
    }


def _load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SourceError(f"{path.name}: {exc}") from exc
