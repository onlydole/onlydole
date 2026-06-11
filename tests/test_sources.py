import json
from pathlib import Path

import pytest

from generator.sources import (
    ACTIVITY_QUERY,
    SourceError,
    _entry_date,
    load_reading,
    load_talks,
    parse_activity,
    parse_goodreads,
    parse_substack,
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


def test_load_talks_sorts_desc_and_caps_at_three(tmp_path):
    talks = tmp_path / "talks.yaml"
    talks.write_text(
        "\n".join(
            f'- {{title: "T{i}", venue: "V", date: 2026-01-0{i}, url: "https://x/{i}"}}'
            for i in (2, 4, 1, 3)
        ),
        encoding="utf-8",
    )
    loaded = load_talks(talks)
    assert [t["title"] for t in loaded] == ["T4", "T3", "T2"]
    assert loaded[0]["kind"] == "talk"


def test_load_talks_missing_field_raises(tmp_path):
    talks = tmp_path / "talks.yaml"
    talks.write_text('- {title: "T", venue: "V", date: 2026-01-01}', encoding="utf-8")
    with pytest.raises(SourceError):
        load_talks(talks)


def test_load_reading_returns_current(tmp_path):
    reading = tmp_path / "reading.yaml"
    reading.write_text(
        'current: {title: "Book", author: "Author", note: "Why I like it"}',
        encoding="utf-8",
    )
    book = load_reading(reading)
    assert book == {
        "title": "Book",
        "author": "Author",
        "url": "",
        "note": "Why I like it",
    }


def test_load_reading_missing_author_raises(tmp_path):
    reading = tmp_path / "reading.yaml"
    reading.write_text('current: {title: "Book"}', encoding="utf-8")
    with pytest.raises(SourceError):
        load_reading(reading)


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
