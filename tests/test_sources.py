import json
from pathlib import Path

import pytest

from generator.sources import (
    ACTIVITY_QUERY,
    SourceError,
    _entry_date,
    parse_activity,
    parse_goodreads,
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


def test_parse_substack_garbage_raises():
    with pytest.raises(SourceError):
        parse_substack("complete garbage, not xml")


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


def test_parse_activity_bad_shape_raises():
    with pytest.raises(SourceError):
        parse_activity({"data": {"user": None}})


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
            "user": {
                "repositories": {"nodes": []},
                "pullRequests": {
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
    }
    assert [i["title"] for i in parse_activity(payload)] == ["Live PR"]


def test_entry_date_rejects_out_of_range_dates():
    assert _entry_date((0, 0, 0, 0, 0, 0, 0, 0, 0)) is None
    assert _entry_date(None) is None
    assert _entry_date((2026, 6, 8, 12, 0, 0, 0, 160, 0)) == "2026-06-08"


def test_activity_query_requests_multiple_releases_per_repo():
    assert "releases(first: 3" in ACTIVITY_QUERY


def test_parse_goodreads_extracts_books():
    books = parse_goodreads((FIXTURES / "goodreads.xml").read_text(encoding="utf-8"))
    assert len(books) == 2
    assert books[0]["title"] == (
        "Obviously Awesome: How to Nail Product Positioning "
        "so Customers Get it, Buy it, Love it"
    )
    assert books[0]["author"] == "April Dunford"
    assert books[0]["url"].startswith("https://www.goodreads.com/review/show/")
    assert books[0]["image_url"].endswith("_SY475_.jpg")


def test_parse_goodreads_garbage_raises():
    with pytest.raises(SourceError):
        parse_goodreads("complete garbage, not xml")


def test_parse_goodreads_caps_at_three():
    item = (
        "<item><title>B{i}</title><author_name>A</author_name>"
        "<link>https://x/{i}</link></item>"
    )
    feed = (
        "<rss><channel>"
        + "".join(item.format(i=i) for i in range(5))
        + "</channel></rss>"
    )
    assert len(parse_goodreads(feed)) == 3


def test_parse_goodreads_image_falls_back_to_small():
    feed = (
        "<rss><channel><item><title>B</title><author_name>A</author_name>"
        "<link>https://x</link><book_image_url>small.jpg</book_image_url>"
        "</item></channel></rss>"
    )
    assert parse_goodreads(feed)[0]["image_url"] == "small.jpg"


def test_parse_goodreads_rejects_doctype_and_entities():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
        "<rss><channel><item><title>&lol;</title>"
        "<author_name>A</author_name><link>https://x</link>"
        "</item></channel></rss>"
    )
    with pytest.raises(SourceError):
        parse_goodreads(bomb)
