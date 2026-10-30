import json
from pathlib import Path

import httpx
import pytest

from generator import sources
from generator.sources import (
    ACTIVITY_QUERY,
    PR_SEARCH,
    SourceError,
    _entry_date,
    parse_activity,
    parse_readwise,
    parse_substack,
    parse_talks,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_substack_takes_three_newest():
    posts = parse_substack((FIXTURES / "substack.xml").read_text(encoding="utf-8"))
    assert [p["title"] for p in posts] == [
        "Newest fixture post",
        "Middle fixture post",
        "Oldest fixture post",
    ]
    assert posts[0]["url"] == "https://onlydole.substack.com/p/newest"
    assert posts[0]["date"] == "2026-06-08"


def test_parse_substack_skips_bad_entries_without_shrinking():
    items = "".join(
        f"<item><title>Post {n}</title>"
        f"<link>https://onlydole.substack.com/p/{n}</link>"
        f"<pubDate>Mon, 0{n} Jun 2026 12:00:00 GMT</pubDate></item>"
        for n in (1, 2, 3)
    )
    feed = (
        "<rss><channel>"
        "<item><title>No date or link</title></item>"
        f"{items}"
        "</channel></rss>"
    )
    posts = parse_substack(feed)
    assert [p["title"] for p in posts] == ["Post 3", "Post 2", "Post 1"]


def test_substack_blocked_rss_uses_public_archive(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        request = httpx.Request("GET", url)
        if url.endswith("/feed"):
            return httpx.Response(403, request=request)
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "title": "Older",
                    "canonical_url": "https://s/older",
                    "post_date": "2026-06-01T12:00:00Z",
                },
                {
                    "title": "New",
                    "canonical_url": "https://s/new",
                    "post_date": "2026-09-05T15:50:36.188Z",
                },
            ],
        )

    monkeypatch.setattr(sources.httpx, "get", get)
    newest = sources.fetch_substack()[0]
    assert newest["title"] == "New"
    assert newest["published_at"] == "2026-09-05T15:50:36+00:00"
    assert calls == [
        sources.SUBSTACK_FEED,
        "https://onlydole.substack.com/api/v1/archive",
    ]


def test_substack_both_endpoints_blocked_raise(monkeypatch):
    monkeypatch.setattr(
        sources.httpx,
        "get",
        lambda url, **kwargs: httpx.Response(403, request=httpx.Request("GET", url)),
    )
    with pytest.raises(SourceError, match="Substack unavailable"):
        sources.fetch_substack()


def _responses(monkeypatch, *outcomes):
    """Serve each outcome in turn; an exception instance is raised."""
    calls = []

    def get(url, **kwargs):
        outcome = outcomes[len(calls)]
        calls.append(url)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("GET", url), text="ok")

    monkeypatch.setattr(sources.httpx, "get", get)
    return calls


def test_send_retries_server_errors_and_dropped_connections(monkeypatch):
    calls = _responses(monkeypatch, 500, httpx.ConnectError("refused"), 200)
    assert sources._send("GET", "https://feed").text == "ok"
    assert len(calls) == 3


def test_send_retries_a_connection_reset_mid_request(monkeypatch):
    calls = _responses(monkeypatch, httpx.ReadError("reset"), 200)
    assert sources._send("GET", "https://feed").text == "ok"
    assert len(calls) == 2


def test_send_does_not_retry_timeouts(monkeypatch):
    calls = _responses(monkeypatch, httpx.ReadTimeout("slow"))
    with pytest.raises(httpx.ReadTimeout):
        sources._send("GET", "https://feed")
    assert len(calls) == 1


def test_send_gives_up_after_the_last_retry(monkeypatch):
    calls = _responses(monkeypatch, 503, 502, 500)
    with pytest.raises(httpx.HTTPStatusError):
        sources._send("GET", "https://feed")
    assert len(calls) == len(sources.RETRY_DELAYS) + 1


def test_send_does_not_retry_a_block(monkeypatch):
    calls = _responses(monkeypatch, 403)
    with pytest.raises(httpx.HTTPStatusError):
        sources._send("GET", "https://substack")
    assert len(calls) == 1


def test_public_search_is_used_before_private_activity_can_crowd_it_out():
    assert "is:public" in PR_SEARCH
    assert f"author:{sources.GITHUB_LOGIN}" in PR_SEARCH
    assert f"-repo:{sources.PROFILE_REPO}" in PR_SEARCH
    assert "$prSearch" in ACTIVITY_QUERY


def test_fetch_activity_sends_the_public_search(monkeypatch):
    sent = {}

    def post(url, **kwargs):
        sent.update(kwargs["json"]["variables"])
        payload = json.loads((FIXTURES / "activity.json").read_text())
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(sources.httpx, "post", post)
    assert sources.fetch_activity("token")[0]["title"] == "Fix scheduler docs"
    assert sent == {"login": sources.GITHUB_LOGIN, "prSearch": PR_SEARCH}


def test_parse_substack_garbage_raises():
    with pytest.raises(SourceError):
        parse_substack("complete garbage, not xml")


def test_substack_orders_same_day_and_keeps_newest_duplicate():
    feed = (
        "<rss><channel>"
        + "".join(
            f"<item><title>{title}</title><link>https://s/{url}</link>"
            f"<pubDate>Mon, 07 Sep 2026 {hour}:00:00 GMT</pubDate></item>"
            for title, url, hour in [
                ("Morning", "one", "08"),
                ("Evening", "two", "20"),
                ("Old copy", "two", "06"),
            ]
        )
        + "</channel></rss>"
    )
    assert [p["title"] for p in parse_substack(feed)] == ["Evening", "Morning"]


def test_parse_activity_merges_sorts_and_caps():
    payload = json.loads((FIXTURES / "activity.json").read_text(encoding="utf-8"))
    items = parse_activity(payload)
    assert [i["title"] for i in items] == [
        "Fix scheduler docs",
        "demo-repo v1.2.0",
        "older-repo v0.3.0",
    ]
    assert items[0]["date"] == "2026-06-07"
    assert items[0]["detail"] == "merged · kubernetes/website"
    assert items[1]["detail"] == "release"


def test_parse_activity_skips_private_and_profile_repo():
    payload = json.loads((FIXTURES / "activity.json").read_text(encoding="utf-8"))
    titles = [i["title"] for i in parse_activity(payload)]
    assert "Secret work" not in titles
    assert "Profile tweak" not in titles
    assert "onlydole v9.9.9" not in titles


def test_parse_activity_orders_same_day_items_by_time():
    payload = {
        "data": {
            "publicPullRequests": {
                "nodes": [
                    {
                        "title": "Morning",
                        "url": "https://x/1",
                        "mergedAt": "2026-06-07T08:00:00Z",
                        "repository": {"nameWithOwner": "a/b", "isPrivate": False},
                    }
                ]
            },
            "user": {
                "repositories": {
                    "nodes": [
                        {
                            "nameWithOwner": "onlydole/tool",
                            "releases": {
                                "nodes": [
                                    {
                                        "tagName": "v2",
                                        "publishedAt": "2026-06-07T20:00:00Z",
                                        "url": "https://x/r",
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
        }
    }
    items = parse_activity(payload)
    assert [i["title"] for i in items] == ["tool v2", "Morning"]
    assert all("_at" not in item for item in items)


def test_parse_activity_bad_shape_raises():
    with pytest.raises(SourceError):
        parse_activity({"data": {"user": None}})
    with pytest.raises(SourceError):
        parse_activity(
            {
                "data": {
                    "publicPullRequests": {"nodes": [None]},
                    "user": {"repositories": {"nodes": []}},
                }
            }
        )


def test_fetch_activity_invalid_json_raises_source_error(monkeypatch):
    response = httpx.Response(
        200,
        content=b"not-json",
        request=httpx.Request("POST", sources.GRAPHQL_URL),
    )
    monkeypatch.setattr(sources.httpx, "post", lambda *args, **kwargs: response)

    with pytest.raises(SourceError, match="invalid JSON"):
        sources.fetch_activity("test-token")


def test_fetch_activity_invalid_encoding_raises_source_error(monkeypatch):
    response = httpx.Response(
        200,
        content=b"\xff",
        request=httpx.Request("POST", sources.GRAPHQL_URL),
    )
    monkeypatch.setattr(sources.httpx, "post", lambda *args, **kwargs: response)

    with pytest.raises(SourceError, match="invalid JSON"):
        sources.fetch_activity("test-token")


def test_fetch_activity_non_object_json_raises_source_error(monkeypatch):
    response = httpx.Response(
        200,
        json=[],
        request=httpx.Request("POST", sources.GRAPHQL_URL),
    )
    monkeypatch.setattr(sources.httpx, "post", lambda *args, **kwargs: response)

    with pytest.raises(SourceError, match="JSON object"):
        sources.fetch_activity("test-token")


def test_parse_talks_extracts_fields():
    talks = parse_talks((FIXTURES / "talks.xml").read_text(encoding="utf-8"))
    assert len(talks) == 3
    assert talks[0] == {
        "title": "The Missing Manual for Open Source Community Sustainability",
        "venue": "KubeCon + CloudNativeCon North America, Atlanta",
        "date": "2025-11-11",
        "url": "https://youtu.be/FPQB7hQL4Vw",
        "kind": "talk",
    }


def test_parse_talks_sorts_desc_and_caps_at_three():
    talks = parse_talks((FIXTURES / "talks.xml").read_text(encoding="utf-8"))
    assert [t["date"] for t in talks] == ["2025-11-11", "2025-11-03", "2025-03-27"]


def test_parse_talks_defaults_kind_and_skips_incomplete_items():
    feed = (
        "<rss><channel>"
        "<item><title>No venue</title><link>https://x/1</link>"
        "<pubDate>Tue, 11 Nov 2025 12:00:00 +0000</pubDate></item>"
        "<item><title>Good</title><link>https://x/2</link>"
        "<description>Venue</description>"
        "<pubDate>Mon, 03 Nov 2025 12:00:00 +0000</pubDate></item>"
        "</channel></rss>"
    )
    talks = parse_talks(feed)
    assert [t["title"] for t in talks] == ["Good"]
    assert talks[0]["kind"] == "talk"
    assert talks[0]["date"] == "2025-11-03"


def test_parse_talks_bad_pubdate_skipped():
    feed = (
        "<rss><channel>"
        "<item><title>Bad date</title><link>https://x/1</link>"
        "<description>V</description><pubDate>not a date</pubDate></item>"
        "<item><title>Overflow date</title><link>https://x/3</link>"
        "<description>V</description>"
        "<pubDate>Tue, 11 Nov 99999999999999 12:00:00 +0000</pubDate></item>"
        "<item><title>Good</title><link>https://x/2</link>"
        "<description>V</description>"
        "<pubDate>Mon, 03 Nov 2025 12:00:00 +0000</pubDate></item>"
        "</channel></rss>"
    )
    assert [t["title"] for t in parse_talks(feed)] == ["Good"]


def test_parse_talks_garbage_raises():
    with pytest.raises(SourceError):
        parse_talks("complete garbage, not xml")


def test_parse_talks_empty_feed_raises():
    with pytest.raises(SourceError):
        parse_talks("<rss><channel></channel></rss>")


def test_parse_talks_rejects_doctype_and_entities():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
        "<rss><channel><item><title>&lol;</title><link>https://x</link>"
        "<description>V</description>"
        "<pubDate>Tue, 11 Nov 2025 12:00:00 +0000</pubDate></item></channel></rss>"
    )
    with pytest.raises(SourceError):
        parse_talks(bomb)


def test_parse_activity_skips_deleted_repo_prs():
    payload = {
        "data": {
            "user": {"repositories": {"nodes": []}},
            "publicPullRequests": {
                "nodes": [
                    {
                        "title": "Ghost PR",
                        "url": "https://x/1",
                        "mergedAt": "2026-01-01T00:00:00Z",
                        "repository": None,
                    },
                    {
                        "title": "Live PR",
                        "url": "https://x/2",
                        "mergedAt": "2026-01-02T00:00:00Z",
                        "repository": {
                            "nameWithOwner": "a/b",
                            "isPrivate": False,
                        },
                    },
                ]
            },
        }
    }
    assert [i["title"] for i in parse_activity(payload)] == ["Live PR"]


def test_entry_date_rejects_out_of_range_dates():
    assert _entry_date((0, 0, 0, 0, 0, 0, 0, 0, 0)) is None
    assert _entry_date(None) is None
    assert _entry_date((2026, 6, 8, 12, 0, 0, 0, 160, 0)) == "2026-06-08"


def test_activity_query_requests_multiple_releases_per_repo():
    assert "releases(first: 3" in ACTIVITY_QUERY


def _readwise_page() -> dict:
    return json.loads((FIXTURES / "readwise.json").read_text(encoding="utf-8"))


def test_parse_readwise_keeps_feed_order_and_links():
    books = parse_readwise(_readwise_page())
    assert [b["title"] for b in books] == [
        "Vibe",
        "A Parade of Horribles: Dungeon Crawler Carl, Book 8",
    ]
    assert books[0] == {
        "title": "Vibe",
        "author": "Adam Grant",
        "url": "https://readwise.io/books/9798217059713/",
        "image_url": "https://bookwise.com/product/cover/577209404860507229/vibe-adam-grant",
    }


def test_readwise_book_without_product_has_no_link_or_cover():
    book = parse_readwise(_readwise_page())[1]
    assert book["url"] == ""
    assert book["image_url"] == ""
    assert book["author"] == "Matt Dinniman"


def test_readwise_caps_at_three_and_skips_other_shelves_and_untitled():
    book = _readwise_page()["results"][1]
    page = {
        "results": [
            {**book, "title": "Done", "status": "finished"},
            {**book, "title": "  "},
            *({**book, "title": f"B{i}"} for i in range(4)),
        ]
    }
    assert [b["title"] for b in parse_readwise(page)] == ["B0", "B1", "B2"]


def test_readwise_falls_back_to_product_title_and_drops_non_https_links():
    page = _readwise_page()
    first = page["results"][0]
    first["title"] = None
    first["author"] = None
    first["product"]["store_url"] = "javascript:alert(1)"
    first["product"]["cover_url"] = "http://insecure/cover.jpg"
    book = parse_readwise(page)[0]
    assert (book["title"], book["author"]) == ("Vibe", "Adam Grant")
    assert book["url"] == book["image_url"] == ""


def test_empty_readwise_shelf_is_valid():
    assert parse_readwise({"results": [], "next": None}) == []


@pytest.mark.parametrize("payload", [None, [], {"detail": "Invalid token."}])
def test_readwise_rejects_responses_without_results(payload):
    with pytest.raises(SourceError, match="no results list"):
        parse_readwise(payload)


def test_fetch_readwise_sends_token_and_shelf(monkeypatch):
    sent = {}

    def get(url, **kwargs):
        sent.update(url=url, **kwargs)
        return httpx.Response(
            200, request=httpx.Request("GET", url), json=_readwise_page()
        )

    monkeypatch.setattr(sources.httpx, "get", get)
    assert sources.fetch_readwise("bwpub_test")[0]["title"] == "Vibe"
    assert sent["url"] == sources.READWISE_FEED
    assert sent["headers"]["Books-Public-Token"] == "bwpub_test"
    assert sent["params"] == {
        "status": "currently_reading",
        "order": "-started_reading_at",
        "limit": 6,
    }


def test_fetch_readwise_wraps_auth_failures(monkeypatch):
    monkeypatch.setattr(
        sources.httpx,
        "get",
        lambda url, **kwargs: httpx.Response(401, request=httpx.Request("GET", url)),
    )
    with pytest.raises(SourceError, match="readwise fetch failed"):
        sources.fetch_readwise("revoked")
