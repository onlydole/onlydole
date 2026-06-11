import json

import pytest

from generator import build, sources

README_FRAME = (
    "<!-- bento:start --><!-- bento:end -->\n"
    "prose stays\n"
    "<sub><!-- stamp:start --><!-- stamp:end --></sub>\n"
)

WRITING = [{"title": "Post", "url": "https://s/p", "date": "2026-06-08"}]
SHIPPED = [
    {
        "title": "repo v1",
        "detail": "release",
        "url": "https://g/r",
        "date": "2026-06-05",
    }
]
TALKS = [
    {
        "title": "Talk",
        "venue": "Conf",
        "date": "2026-04-01",
        "url": "https://t/1",
        "kind": "talk",
    }
]
READING = {"title": "Book", "author": "Author", "url": "", "note": ""}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text(README_FRAME, encoding="utf-8")
    assets = tmp_path / "assets"
    monkeypatch.setattr(build, "README", readme)
    monkeypatch.setattr(build, "ASSETS", assets)
    monkeypatch.setattr(build, "CACHE", assets / "data-cache.json")
    monkeypatch.setenv("BUILD_DATE", "2026-06-10")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    return tmp_path


def _patch_sources(monkeypatch, writing=WRITING):
    monkeypatch.setattr(sources, "fetch_substack", lambda: writing)
    monkeypatch.setattr(sources, "fetch_activity", lambda token: SHIPPED)
    monkeypatch.setattr(sources, "load_talks", lambda path=None: TALKS)
    monkeypatch.setattr(sources, "load_reading", lambda path=None: READING)


def test_main_builds_assets_readme_and_cache(workspace, monkeypatch):
    _patch_sources(monkeypatch)
    assert build.main() == 0
    readme = build.README.read_text(encoding="utf-8")
    assert 'srcset="assets/writing-dark.svg"' in readme
    assert '<a href="https://s/p">' in readme
    assert "Last refreshed: 2026-06-10" in readme
    assert "prose stays" in readme
    for name in (
        "hero.svg",
        "writing-dark.svg",
        "writing-light.svg",
        "shipped-dark.svg",
        "shipped-light.svg",
        "stage-dark.svg",
        "stage-light.svg",
        "reading-dark.svg",
        "reading-light.svg",
        "chip-substack-dark.svg",
        "chip-website-light.svg",
    ):
        assert (build.ASSETS / name).exists(), name
    cache = json.loads(build.CACHE.read_text(encoding="utf-8"))
    assert cache["writing"] == WRITING
    assert cache["updated"] == "2026-06-10"


def test_dead_source_falls_back_to_cache(workspace, monkeypatch):
    _patch_sources(monkeypatch)
    assert build.main() == 0

    def boom():
        raise sources.SourceError("substack is down")

    _patch_sources(monkeypatch)
    monkeypatch.setattr(sources, "fetch_substack", boom)
    monkeypatch.setenv("BUILD_DATE", "2026-06-11")
    assert build.main() == 0
    second = build.README.read_text(encoding="utf-8")
    assert '<a href="https://s/p">' in second  # cached writing link survives
    assert "Last refreshed: 2026-06-11" in second  # stamp still advanced


def test_dead_source_with_no_cache_renders_empty_state(workspace, monkeypatch):
    _patch_sources(monkeypatch)

    def boom():
        raise sources.SourceError("substack is down")

    monkeypatch.setattr(sources, "fetch_substack", boom)
    assert build.main() == 0
    readme = build.README.read_text(encoding="utf-8")
    assert '<a href="https://onlydole.substack.com">' in readme  # fallback link


def test_corrupted_cache_is_ignored(workspace, monkeypatch):
    _patch_sources(monkeypatch)
    build.ASSETS.mkdir(parents=True, exist_ok=True)
    build.CACHE.write_text("{not valid json", encoding="utf-8")
    assert build.main() == 0
    cache = json.loads(build.CACHE.read_text(encoding="utf-8"))
    assert cache["writing"] == WRITING


def test_summary_uses_secondary_alone_when_primary_empty():
    assert build._summary([{"primary": "", "secondary": "a note"}]) == "a note"


def test_tile_contexts_treats_incomplete_reading_as_missing():
    tiles = build.tile_contexts({"reading": {}})
    reading = next(t for t in tiles if t["key"] == "reading")
    assert reading["lines"] == build.EMPTY_LINES
    assert reading["url"] == ""
