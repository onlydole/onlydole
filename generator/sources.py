"""Fetch and parse the four content sources."""

from __future__ import annotations

import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import feedparser
import httpx

SUBSTACK_FEED = "https://onlydole.substack.com/feed"
GITHUB_LOGIN = "onlydole"
PROFILE_REPO = "onlydole/onlydole"
GRAPHQL_URL = "https://api.github.com/graphql"
GOODREADS_USER_ID = "22801001"
GOODREADS_FEED = (
    "https://www.goodreads.com/review/list_rss/"
    f"{GOODREADS_USER_ID}?shelf=currently-reading"
)
TALKS_FEED = "https://onlydole.dev/feeds/talks.xml"
USER_AGENT = "Mozilla/5.0 (compatible; onlydole-profile-bot/1.0)"


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


def _rfc822_date(value: str | None) -> str | None:
    """ISO date from an RFC 822 pubDate, or None if absent/invalid.

    OverflowError covers absurd years (e.g. 14 digits), which
    parsedate_to_datetime raises instead of ValueError.
    """
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def parse_talks(feed_text: str) -> list[dict]:
    """Parse the onlydole.dev talks RSS feed into up to 3 talk dicts.

    Same DTD and entity rejection guard as parse_goodreads. The feed
    carries the venue in each item's description and the kind in its
    category, per the producer spec in onlydole.github.io.
    """
    lowered = feed_text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise SourceError("feed contains DTD or entity declarations")
    try:
        root = ElementTree.fromstring(feed_text)
    except ElementTree.ParseError as exc:
        raise SourceError(f"unparsable talks feed: {exc}") from exc
    talks = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        venue = (item.findtext("description") or "").strip()
        kind = (item.findtext("category") or "").strip() or "talk"
        date = _rfc822_date(item.findtext("pubDate"))
        if not (title and url and venue and date):
            continue
        talks.append(
            {"title": title, "venue": venue, "date": date, "url": url, "kind": kind}
        )
    if not talks:
        raise SourceError("talks feed had no usable items")
    talks.sort(key=lambda t: t["date"], reverse=True)
    return talks[:3]


def fetch_talks() -> list[dict]:
    try:
        resp = httpx.get(
            TALKS_FEED,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceError(f"talks fetch failed: {exc}") from exc
    return parse_talks(resp.text)


def parse_goodreads(feed_text: str) -> list[dict]:
    """Parse a Goodreads shelf RSS feed into up to 3 book dicts.

    Rejects any document carrying DTD or entity declarations before
    parsing. That closes the XXE and entity-expansion attack classes
    without a defusedxml dependency, and real Goodreads feeds never
    include a DOCTYPE. Python 3.12's expat amplification limits are the
    second layer.
    """
    lowered = feed_text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise SourceError("feed contains DTD or entity declarations")
    try:
        root = ElementTree.fromstring(feed_text)
    except ElementTree.ParseError as exc:
        raise SourceError(f"unparsable goodreads feed: {exc}") from exc
    books = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        author = (item.findtext("author_name") or "").strip()
        url = (item.findtext("link") or "").strip()
        image = (item.findtext("book_large_image_url") or "").strip() or (
            item.findtext("book_image_url") or ""
        ).strip()
        if not (title and author and url):
            continue
        books.append({"title": title, "author": author, "url": url, "image_url": image})
        if len(books) == 3:
            break
    if not books:
        raise SourceError("goodreads shelf feed had no usable items")
    return books


def fetch_goodreads() -> list[dict]:
    try:
        resp = httpx.get(
            GOODREADS_FEED,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SourceError(f"goodreads fetch failed: {exc}") from exc
    return parse_goodreads(resp.text)
