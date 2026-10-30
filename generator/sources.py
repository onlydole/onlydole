"""Fetch public feeds and public GitHub activity."""

from __future__ import annotations

import datetime
import json
import time
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import feedparser
import httpx

SUBSTACK_FEED = "https://onlydole.substack.com/feed"
PODCAST_FEED = "https://attentiondeficitpod.substack.com/feed"
GITHUB_LOGIN = "onlydole"
PROFILE_REPO = "onlydole/onlydole"
GRAPHQL_URL = "https://api.github.com/graphql"
# The Readwise Books account id. The public feed also needs a public token,
# which the build reads from READWISE_BOOKS_TOKEN.
READWISE_PROFILE_ID = "644961"
READWISE_FEED = f"https://readwise.io/books/api/v1/public/{READWISE_PROFILE_ID}/books"
TALKS_FEED = "https://onlydole.dev/feeds/talks.xml"
USER_AGENT = "Mozilla/5.0 (compatible; onlydole-profile-bot/1.0)"


# Waits between attempts. Only 429 and 5xx answers and dropped connections
# are retried; those come back fast, so a flaky source adds seconds, not
# minutes, to the ten-minute job.
RETRY_DELAYS = (2, 5)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_sleep = time.sleep


class SourceError(RuntimeError):
    """A content source could not be fetched or parsed."""


def _send(method: str, url: str, **kwargs) -> httpx.Response:
    """Send a request and raise for its final status, retrying transient errors.

    A 4xx such as Substack's 403 is a policy answer and fails at once.
    Timeouts aren't retried because each request already waits 30 seconds.
    """
    send = httpx.post if method == "POST" else httpx.get
    for delay in RETRY_DELAYS:
        try:
            resp = send(url, **kwargs)
        except (httpx.NetworkError, httpx.RemoteProtocolError):
            pass
        else:
            if resp.status_code not in RETRY_STATUSES:
                break
        _sleep(delay)
    else:
        resp = send(url, **kwargs)
    resp.raise_for_status()
    return resp


def _entry_date(published) -> str | None:
    """ISO date from a feedparser struct_time, or None if absent/invalid."""
    try:
        return datetime.date(*published[:3]).isoformat()
    except (TypeError, ValueError):
        return None


def _published_fields(value: datetime.datetime) -> dict:
    """Whole-second UTC, so every route stamps the same post identically.

    The archive reports milliseconds and RSS doesn't. gather compares
    stamps as strings, where "28+00:00" sorts before "28.942000+00:00".
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.UTC)
    value = value.astimezone(datetime.UTC).replace(microsecond=0)
    return {"date": value.date().isoformat(), "published_at": value.isoformat()}


def _newest_posts(posts: list[dict]) -> list[dict]:
    posts.sort(key=lambda p: p.get("published_at", p["date"]), reverse=True)
    unique = {}
    for post in posts:
        unique.setdefault(post["url"], post)
    return list(unique.values())[:3]


def parse_substack(feed_text: str) -> list[dict]:
    parsed = feedparser.parse(feed_text)
    if parsed.bozo and not parsed.entries:
        raise SourceError(f"unparsable feed: {parsed.bozo_exception}")
    posts = []
    for entry in parsed.entries:
        date = _entry_date(entry.get("published_parsed"))
        if not (entry.get("title") and entry.get("link") and date):
            continue
        posts.append(
            {
                "title": entry["title"],
                "url": entry["link"],
                **_published_fields(
                    datetime.datetime(
                        *entry["published_parsed"][:6], tzinfo=datetime.UTC
                    )
                ),
            }
        )
    if not posts:
        raise SourceError("feed contained no usable entries")
    return _newest_posts(posts)


def _fetch_substack_rss(feed_url: str) -> list[dict]:
    resp = _send(
        "GET",
        feed_url,
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml",
        },
    )
    return parse_substack(resp.text)


def _fetch_substack_archive(feed_url: str) -> list[dict]:
    """Read the publication's public archive endpoint.

    It's a public endpoint, not an authenticated dashboard or paywall bypass.
    """
    resp = _send(
        "GET",
        feed_url.removesuffix("/feed") + "/api/v1/archive",
        params={"sort": "new", "limit": 10},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
        follow_redirects=True,
    )
    payload = resp.json()
    if not isinstance(payload, list):
        raise SourceError("archive response was not a list")
    posts = []
    for post in payload:
        if not isinstance(post, dict):
            continue
        title, url, date = (
            post.get(k) for k in ("title", "canonical_url", "post_date")
        )
        if not all(isinstance(v, str) and v for v in (title, url, date)):
            continue
        published = datetime.datetime.fromisoformat(date)
        posts.append({"title": title, "url": url, **_published_fields(published)})
    if not posts:
        raise SourceError("archive contained no usable posts")
    return _newest_posts(posts)


def fetch_substack(feed_url: str = SUBSTACK_FEED) -> list[dict]:
    """Try RSS, then the public archive.

    Substack blocks hosted runners on both endpoints, so in Actions both
    Substack cards serve their cache. The local refresh job in local/
    fetches them from a network Substack answers.
    """
    errors = []
    for route in (_fetch_substack_rss, _fetch_substack_archive):
        try:
            return route(feed_url)
        except (httpx.HTTPError, ValueError, UnicodeDecodeError, SourceError) as exc:
            name = route.__name__.removeprefix("_fetch_substack_")
            detail = str(exc).splitlines()[0] if str(exc) else repr(exc)
            errors.append(f"{name}: {detail}")
    raise SourceError(f"Substack unavailable ({'; '.join(errors)})")


def fetch_podcast() -> list[dict]:
    return fetch_substack(PODCAST_FEED)


# Search public PRs before applying the result limit, so private work
# can't crowd public work out of the sample.
PR_SEARCH = (
    f"is:pr is:merged is:public author:{GITHUB_LOGIN} "
    f"-repo:{PROFILE_REPO} sort:updated-desc"
)
ACTIVITY_QUERY = """
query($login: String!, $prSearch: String!) {
  publicPullRequests: search(query: $prSearch, type: ISSUE, first: 100) {
    nodes { ... on PullRequest {
      title url mergedAt repository { nameWithOwner isPrivate }
    } }
  }
  user(login: $login) {
    repositories(first: 50, privacy: PUBLIC, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        nameWithOwner
        releases(first: 3, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { tagName publishedAt url }
        }
      }
    }
  }
}
"""


def parse_activity(payload: dict) -> list[dict]:
    """Merge public releases and merged public PRs, newest first.

    The profile repository is left out: its own refresh commits and
    dashboard tweaks aren't shipped work.
    """
    items = []
    try:
        repo_nodes = payload["data"]["user"]["repositories"]["nodes"]
        pr_nodes = payload["data"]["publicPullRequests"]["nodes"]
        for repo in repo_nodes:
            if repo["nameWithOwner"] == PROFILE_REPO:
                continue
            for release in repo["releases"]["nodes"]:
                if not release.get("publishedAt"):
                    continue
                items.append(
                    {
                        "title": f"{repo['nameWithOwner'].split('/')[-1]} "
                        f"{release['tagName']}",
                        "detail": "release",
                        "url": release["url"],
                        "date": release["publishedAt"][:10],
                        "_at": release["publishedAt"],
                    }
                )
        for pr in pr_nodes:
            repo = pr.get("repository")  # null when the repository was deleted
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
                    "_at": pr["mergedAt"],
                }
            )
    except (KeyError, TypeError, AttributeError) as exc:
        raise SourceError(f"unexpected GraphQL shape: {exc!r}") from exc
    if not items:
        raise SourceError("no public activity found")
    items.sort(key=lambda item: item["_at"], reverse=True)
    return [{k: v for k, v in item.items() if k != "_at"} for item in items[:3]]


def fetch_activity(token: str) -> list[dict]:
    try:
        resp = _send(
            "POST",
            GRAPHQL_URL,
            json={
                "query": ACTIVITY_QUERY,
                "variables": {"login": GITHUB_LOGIN, "prSearch": PR_SEARCH},
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise SourceError(f"github fetch failed: {exc}") from exc
    try:
        payload = resp.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceError(f"github returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SourceError("github response was not a JSON object")
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

    Rejects any document carrying DTD or entity declarations before
    parsing, which closes the XXE and entity-expansion attack classes
    without a defusedxml dependency. The feed
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
        resp = _send(
            "GET",
            TALKS_FEED,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    except httpx.HTTPError as exc:
        raise SourceError(f"talks fetch failed: {exc}") from exc
    return parse_talks(resp.text)


def parse_readwise(payload: object) -> list[dict]:
    """Parse a Readwise Books public feed page into up to 3 book dicts.

    The feed is requested newest start first, so its order is kept. A book
    without a matched catalog product has no store link or cover.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SourceError("readwise response had no results list")
    books = []
    for book in payload["results"]:
        if not isinstance(book, dict) or book.get("status") != "currently_reading":
            continue
        product = book.get("product") if isinstance(book.get("product"), dict) else {}
        title = book.get("title") or product.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        author = book.get("author") or product.get("author") or ""
        books.append(
            {
                "title": title.strip(),
                "author": author.strip() if isinstance(author, str) else "",
                "url": _https_or_empty(product.get("store_url")),
                "image_url": _https_or_empty(product.get("cover_url")),
            }
        )
    return books[:3]


def _https_or_empty(value: object) -> str:
    return value if isinstance(value, str) and value.startswith("https://") else ""


def fetch_readwise(token: str) -> list[dict]:
    try:
        resp = _send(
            "GET",
            READWISE_FEED,
            params={
                "status": "currently_reading",
                "order": "-started_reading_at",
                "limit": 3,
            },
            headers={"Books-Public-Token": token, "User-Agent": USER_AGENT},
            timeout=30,
        )
        payload = resp.json()
    except (httpx.HTTPError, ValueError, UnicodeDecodeError) as exc:
        raise SourceError(f"readwise fetch failed: {exc}") from exc
    return parse_readwise(payload)
