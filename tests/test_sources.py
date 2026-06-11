import json
from pathlib import Path

import pytest

from generator.sources import SourceError, parse_activity, parse_substack

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
