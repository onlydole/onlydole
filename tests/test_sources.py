import json
from pathlib import Path

import pytest

from generator.sources import (
    SourceError,
    load_reading,
    load_talks,
    parse_activity,
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
