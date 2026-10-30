"""Fetch public feeds and public GitHub activity."""

from __future__ import annotations

import datetime
import json
import re
import time
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from xml.etree import ElementTree

import feedparser
import httpx

SUBSTACK_FEED = "https://onlydole.substack.com/feed"
PODCAST_FEED = "https://attentiondeficitpod.substack.com/feed"
RSS_RELAY = "https://api.rss2json.com/v1/api.json"
GITHUB_LOGIN = "onlydole"
PROFILE_REPO = "onlydole/onlydole"
GRAPHQL_URL = "https://api.github.com/graphql"
GOODREADS_USER_ID = "22801001"
# Shelf and review pages need sign-in. Profiles and book pages don't.
GOODREADS_PROFILE = f"https://www.goodreads.com/user/show/{GOODREADS_USER_ID}"
GOODREADS_BOOK = "https://www.goodreads.com/book/show/"
_BOOK_PATH = re.compile(r"(?:https://www\.goodreads\.com)?/book/show/(\d+[\w.-]*)")
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

    The archive reports milliseconds and the relay doesn't. gather compares
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
    """Try RSS, then the public archive, then the public RSS relay.

    Substack blocks hosted runners on both of its own endpoints, so the
    relay is the route that usually answers in Actions.
    """
    errors = []
    for route in (_fetch_substack_rss, _fetch_substack_archive):
        try:
            return route(feed_url)
        except (httpx.HTTPError, ValueError, UnicodeDecodeError, SourceError) as exc:
            name = route.__name__.removeprefix("_fetch_substack_")
            detail = str(exc).splitlines()[0] if str(exc) else repr(exc)
            errors.append(f"{name}: {detail}")
    print(f"Substack direct fetch unavailable ({'; '.join(errors)}); trying relay")
    return fetch_substack_relay(feed_url)


def fetch_substack_relay(feed_url: str) -> list[dict]:
    """Last network fallback for hosted runners blocked by Substack.

    The relay receives only a public feed URL. Its content may be cached;
    gather rejects snapshots older than the already-verified local cache.
    """
    try:
        resp = _send("GET", RSS_RELAY, params={"rss_url": feed_url}, timeout=30)
        payload = resp.json()
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise SourceError("RSS relay did not return a successful feed")
        feed = payload.get("feed")
        if not isinstance(feed, dict) or feed.get("url") != feed_url:
            raise SourceError("RSS relay returned a different publication")
        if not isinstance(payload.get("items"), list):
            raise SourceError("RSS relay had no item list")
        posts = []
        for item in payload["items"]:
            if not isinstance(item, dict):
                continue
            title, url, date = (item.get(k) for k in ("title", "link", "pubDate"))
            if not all(isinstance(v, str) and v for v in (title, url, date)):
                continue
            if not url.startswith(feed_url.removesuffix("/feed") + "/p/"):
                continue
            try:
                published = datetime.datetime.fromisoformat(date)
            except ValueError:
                continue
            posts.append(
                {
                    "title": title,
                    "url": url,
                    **_published_fields(published),
                    "via": "rss2json",
                }
            )
        if not posts:
            raise SourceError("RSS relay contained no usable posts")
        return _newest_posts(posts)
    except (httpx.HTTPError, ValueError, UnicodeDecodeError, SourceError) as exc:
        raise SourceError(f"Substack and public RSS relay unavailable: {exc}") from exc


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
    parsing. That closes the XXE and entity-expansion attack classes
    without a defusedxml dependency. The feed carries the venue in each
    item's description and the kind in its category, per the producer
    spec in onlydole.github.io.
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


class _CurrentlyReading(HTMLParser):
    """Collect books from the profile's Currently Reading box.

    Goodreads renders the box as a div with id="currentlyReadingReviews"
    holding one div.Updates per book, with the cover first, then
    a.bookTitle and a.authorName. Anything outside the box is ignored.
    """

    def __init__(self) -> None:
        super().__init__()
        self.found = False
        self.books: list[dict] = []
        self._depth = 0
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr = {k: v or "" for k, v in attrs}
        classes = set(attr.get("class", "").split())
        if not self._depth:
            if tag == "div" and attr.get("id") == "currentlyReadingReviews":
                self.found = True
                self._depth = 1
            return
        if tag == "div":
            self._depth += 1
            if "Updates" in classes:
                self.books.append({"title": "", "author": "", "href": "", "image": ""})
        if not self.books:
            return
        book = self.books[-1]
        if tag == "img" and not book["image"]:
            book["image"] = attr.get("src", "")
        elif tag == "a" and "bookTitle" in classes and not book["title"]:
            book["href"] = attr.get("href", "")
            self._field = "title"
        elif tag == "a" and "authorName" in classes and not book["author"]:
            self._field = "author"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._field = None
        elif tag == "div" and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._field:
            self.books[-1][self._field] += data


def _book_url(href: str) -> str | None:
    """Public book page for a /book/show/ link, or None for anything else."""
    match = _BOOK_PATH.fullmatch(href)
    return GOODREADS_BOOK + match[1] if match else None


def parse_goodreads(page: str) -> list[dict]:
    """Parse the public profile page into up to 3 currently-reading books.

    Goodreads dropped shelf RSS and put shelf pages behind sign-in in
    October 2026. The profile still shows the shelf to logged-out visitors,
    and the card keeps its order. A page without the box, such as the
    sign-in page or a redesign, raises so the build keeps its cache.
    """
    parser = _CurrentlyReading()
    parser.feed(page)
    parser.close()
    if not parser.found:
        raise SourceError("goodreads profile had no Currently Reading box")
    books = []
    for raw in parser.books:
        title = " ".join(raw["title"].split())
        author = " ".join(raw["author"].split())
        url = _book_url(raw["href"])
        if not (title and author and url):
            continue
        image = raw["image"] if raw["image"].startswith("https://") else ""
        books.append({"title": title, "author": author, "url": url, "image_url": image})
    if not books and parser.books:
        raise SourceError("goodreads Currently Reading box had no usable books")
    return books[:3]


def fetch_goodreads() -> list[dict]:
    try:
        resp = _send(
            "GET",
            GOODREADS_PROFILE,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    except httpx.HTTPError as exc:
        raise SourceError(f"goodreads fetch failed: {exc}") from exc
    return parse_goodreads(resp.text)
