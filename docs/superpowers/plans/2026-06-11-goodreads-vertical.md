# Goodreads Reading Tile + Vertical Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the Reading Now tile from Taylor's public Goodreads currently-reading shelf (with embedded book cover) and convert all four bento tiles from a 2×2 grid of 600px tiles to stacked full-width 1200px rows that eliminate title truncation.

**Architecture:** A new `fetch_goodreads()`/`parse_goodreads()` pair in `generator/sources.py` (stdlib ElementTree, no new deps) replaces the YAML reading loader. `generator/build.py` gains a reading resolver with a cover download pipeline (base64 into the SVG, cached in `data-cache.json`, 80KB cap). The tile template becomes parameterized for width, height, text offset, an optional cover image, and an optional muted header note. Spec at `docs/superpowers/specs/2026-06-11-goodreads-vertical-design.md`.

**Tech Stack:** Python 3.12, uv, httpx, Jinja2, xml.etree.ElementTree, pytest golden files, GitHub Actions.

**Working branch:** `feat/goodreads-vertical` (already created, spec committed). Run all commands from the repo root. Do not push until Task 4 says so. The suite must be green at the end of every task.

---

### Task 1: Goodreads source functions

**Files:**
- Create: `tests/fixtures/goodreads.xml`
- Modify: `generator/sources.py` (append; do NOT touch `load_reading` yet, it dies in Task 3)
- Test: `tests/test_sources.py` (append)

- [ ] **Step 1: Write the feed fixture**

`tests/fixtures/goodreads.xml` (trimmed real shape, captured 2026-06-11):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Taylor's bookshelf: currently-reading</title>
    <item>
      <guid><![CDATA[https://www.goodreads.com/review/show/8658061089?utm_medium=api&utm_source=rss]]></guid>
      <pubDate><![CDATA[Thu, 04 Jun 2026 00:38:25 -0700]]></pubDate>
      <title><![CDATA[Obviously Awesome: How to Nail Product Positioning so Customers Get it, Buy it, Love it]]></title>
      <link><![CDATA[https://www.goodreads.com/review/show/8658061089?utm_medium=api&utm_source=rss]]></link>
      <book_id>247591327</book_id>
      <book_image_url><![CDATA[https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/books/1770225651l/247591327._SY75_.jpg]]></book_image_url>
      <book_large_image_url><![CDATA[https://i.gr-assets.com/images/S/compressed.photo.goodreads.com/books/1770225651l/247591327._SY475_.jpg]]></book_large_image_url>
      <author_name>April Dunford</author_name>
      <user_shelves>currently-reading</user_shelves>
    </item>
    <item>
      <guid><![CDATA[https://www.goodreads.com/review/show/9000000001]]></guid>
      <pubDate><![CDATA[Mon, 01 Jun 2026 09:00:00 -0700]]></pubDate>
      <title><![CDATA[Thinking in Systems]]></title>
      <link><![CDATA[https://www.goodreads.com/review/show/9000000001]]></link>
      <book_id>3828902</book_id>
      <book_image_url><![CDATA[https://i.gr-assets.com/images/S/books/3828902._SY75_.jpg]]></book_image_url>
      <book_large_image_url><![CDATA[https://i.gr-assets.com/images/S/books/3828902._SY475_.jpg]]></book_large_image_url>
      <author_name>Donella H. Meadows</author_name>
      <user_shelves>currently-reading</user_shelves>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_sources.py`:

```python
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
```

Update the import block at the top of `tests/test_sources.py` to include the new name:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --project generator pytest tests/test_sources.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_goodreads'`

- [ ] **Step 4: Implement in `generator/sources.py`**

Add to the imports at the top of the file:

```python
from xml.etree import ElementTree
```

Add constants next to the existing feed constants:

```python
GOODREADS_USER_ID = "22801001"
GOODREADS_FEED = (
    "https://www.goodreads.com/review/list_rss/"
    f"{GOODREADS_USER_ID}?shelf=currently-reading"
)
USER_AGENT = "Mozilla/5.0 (compatible; onlydole-profile-bot/1.0)"
```

Append the functions:

```python
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
        books.append(
            {"title": title, "author": author, "url": url, "image_url": image}
        )
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --project generator pytest tests/test_sources.py -v`
Expected: 17 passed (12 existing + 5 new)

- [ ] **Step 6: Commit**

```bash
git add generator/sources.py tests/fixtures/goodreads.xml tests/test_sources.py
git commit -m "Add Goodreads currently-reading source"
```

---

### Task 2: Wide tile template, geometry, and stacked README layout

**Files:**
- Modify: `generator/templates/tile.svg.j2` (full replacement)
- Modify: `generator/build.py` (geometry constants, `write_assets`, `bento_html`, `tile_contexts` budgets)
- Modify: `tests/golden_cases.py` (full replacement)
- Modify: `tests/goldens/` (regenerated)
- Test: `tests/test_build.py` (one assertion update)

This task keeps the reading tile on the existing YAML loader. Only geometry and layout change here.

- [ ] **Step 1: Replace `generator/templates/tile.svg.j2`**

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {{ width }} {{ height }}" role="img" aria-label="{{ aria }}">
  <rect x="1.5" y="1.5" width="{{ width - 3 }}" height="{{ height - 3 }}" rx="16" fill="{{ theme.bg }}" stroke="{{ theme.border }}" stroke-width="2"/>
{% if cover %}
  <image x="36" y="56" width="92" height="138" preserveAspectRatio="xMidYMid meet" href="data:{{ cover.mime }};base64,{{ cover.b64 }}"/>
{% endif %}
  <text x="{{ text_x }}" y="62" font-family="{{ font }}" font-size="22" font-weight="700" letter-spacing="2.5" fill="{{ theme.accent }}">{{ header }}</text>
{% if header_note %}
  <text x="{{ width - 36 }}" y="62" text-anchor="end" font-family="{{ font }}" font-size="15" fill="{{ theme.muted }}">{{ header_note }}</text>
{% endif %}
{% for line in lines %}
  <text x="{{ text_x }}" y="{{ 122 + loop.index0 * 74 }}" font-family="{{ font }}" font-size="25" fill="{{ theme.text }}">{{ line.primary }}</text>
  <text x="{{ text_x }}" y="{{ 152 + loop.index0 * 74 }}" font-family="{{ font }}" font-size="17" fill="{{ theme.muted }}">{{ line.secondary }}</text>
{% endfor %}
</svg>
```

- [ ] **Step 2: Replace `tests/golden_cases.py`**

```python
"""Fixture contexts shared by the golden test and the regenerator."""

from generator.render import DARK, FONT_STACK, LIGHT

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

CASES = {
    "hero.svg": (
        "hero.svg.j2",
        {
            "font": FONT_STACK,
            "aria": "Taylor Dolezal — Head of Open Source at Dosu · "
            "Open Source Strategy & Ecosystems · Los Angeles",
            "name": "Taylor Dolezal",
            "role": "Head of Open Source @ Dosu · "
            "Open Source Strategy & Ecosystems · Los Angeles",
            "cred": "KubeCon keynoter · ex-Disney Studios SRE · ex-HashiCorp",
        },
    ),
    "tile-writing-dark.svg": (
        "tile.svg.j2",
        {
            "font": FONT_STACK,
            "theme": DARK,
            "width": 1200,
            "height": 262,
            "text_x": 36,
            "cover": None,
            "header_note": "",
            "header": "✍️ LATEST WRITING",
            "aria": "Latest writing: Fixture post (2026-01-02)",
            "lines": [
                {"primary": "Fixture post", "secondary": "2026-01-02"},
                {
                    "primary": "Second post with <angle> & amp",
                    "secondary": "2026-01-01",
                },
            ],
        },
    ),
    "tile-writing-light.svg": (
        "tile.svg.j2",
        {
            "font": FONT_STACK,
            "theme": LIGHT,
            "width": 1200,
            "height": 188,
            "text_x": 36,
            "cover": None,
            "header_note": "",
            "header": "✍️ LATEST WRITING",
            "aria": "Latest writing: Fixture post (2026-01-02)",
            "lines": [{"primary": "Fixture post", "secondary": "2026-01-02"}],
        },
    ),
    "tile-reading-cover-dark.svg": (
        "tile.svg.j2",
        {
            "font": FONT_STACK,
            "theme": DARK,
            "width": 1200,
            "height": 250,
            "text_x": 156,
            "cover": {"mime": "image/png", "b64": TINY_PNG_B64},
            "header_note": "via Goodreads",
            "header": "📚 READING NOW",
            "aria": "Reading now: Fixture book (Fixture author)",
            "lines": [{"primary": "Fixture book", "secondary": "Fixture author"}],
        },
    ),
    "chip-substack-dark.svg": (
        "chip.svg.j2",
        {"font": FONT_STACK, "theme": DARK, "label": "Substack"},
    ),
}
```

- [ ] **Step 3: Run the golden test to verify it fails**

Run: `uv run --project generator pytest tests/test_render.py -v`
Expected: FAIL (template output no longer matches old goldens, plus a missing golden for the new reading-cover case)

- [ ] **Step 4: Update `generator/build.py` geometry and layout**

Add constants below `EMPTY_LINES`:

```python
TILE_WIDTH = 1200
TEXT_X = 36
TEXT_X_WITH_COVER = 156
COVER_MAX_BYTES = 80_000
```

Add the geometry helper above `write_assets`:

```python
def _tile_geometry(tile: dict) -> dict:
    height = 88 + 74 * len(tile["lines"]) + 26
    if tile.get("cover"):
        height = max(height, 250)
    return {
        "width": TILE_WIDTH,
        "height": height,
        "text_x": TEXT_X_WITH_COVER if tile.get("cover") else TEXT_X,
    }
```

In `write_assets`, replace the tile render call so the template receives the new parameters:

```python
    for tile in tiles:
        geometry = _tile_geometry(tile)
        for theme_name, theme in themes:
            svg = render_svg(
                "tile.svg.j2",
                {
                    "font": FONT_STACK,
                    "theme": theme,
                    "lines": tile["lines"],
                    "header": tile["header"],
                    "aria": tile["alt"],
                    "cover": tile.get("cover"),
                    "header_note": tile.get("header_note", ""),
                    **geometry,
                },
            )
            (ASSETS / f"{tile['key']}-{theme_name}.svg").write_text(
                svg, encoding="utf-8"
            )
```

Replace `bento_html` with the stacked version:

```python
def bento_html(tiles: list[dict]) -> str:
    rows = [
        f'<a href="{SITE}"><img src="assets/hero.svg" width="100%" '
        f'alt="{_esc(HERO_ALT)}"></a>'
    ]
    for tile in tiles:
        picture = _picture(tile["key"], tile["alt"], "100%")
        if tile["url"]:
            cell = f'<a href="{_esc(tile["url"])}">{picture}</a>'
        else:
            cell = picture
        rows.append(f'<p align="center">\n  {cell}\n</p>')
    chips = [
        f'<a href="{_esc(url)}">{_picture("chip-" + key, label, "150")}</a>'
        for key, label, url in CHIPS
    ]
    rows.append('<p align="center">\n  ' + "\n  ".join(chips) + "\n</p>")
    return "\n".join(rows)
```

In `tile_contexts`, raise every truncation budget. Writing primary `fit(p["title"], 84)`. Shipped primary `fit(i["title"], 84)` and secondary `fit(f"{i['detail']} · {i['date']}", 110)`. Stage primary `fit(t["title"], 84)` and secondary `fit(f"{t['venue']} · {t['date']}", 110)`. Reading primary `fit(reading["title"], 84)` and note `fit(reading["note"], 110)` (this loader is replaced in Task 3, raise the numbers anyway so the diff stays clean).

- [ ] **Step 5: Regenerate goldens and verify the suite passes**

```bash
uv run --project generator python tests/update_goldens.py
open tests/goldens/tile-writing-dark.svg tests/goldens/tile-reading-cover-dark.svg
uv run --project generator pytest tests/ -v
```

Expected: 5 goldens written, wide tiles look right (skip `open` if running non-interactively and note it), then 36 passed. The old markup assertion still passes because `srcset` survives the layout change, which is exactly why the next step strengthens it.

- [ ] **Step 6: Strengthen the README markup assertion in `tests/test_build.py`**

In `test_main_builds_assets_readme_and_cache`, replace the line

```python
    assert 'srcset="assets/writing-dark.svg"' in readme
```

with

```python
    assert 'srcset="assets/writing-dark.svg"' in readme
    assert 'src="assets/writing-light.svg" width="100%"' in readme
```

- [ ] **Step 7: Run the full suite**

Run: `uv run --project generator pytest tests/ -v`
Expected: 36 passed (31 previous + 5 from Task 1, all green with the new geometry)

- [ ] **Step 8: Commit**

```bash
git add generator/templates/tile.svg.j2 generator/build.py tests/golden_cases.py tests/goldens/ tests/test_build.py
git commit -m "Convert tiles to full-width rows with raised truncation budgets"
```

---

### Task 3: Reading pipeline switch (Goodreads in, YAML out)

**Files:**
- Modify: `generator/build.py` (reading resolver, cover download, gather, tile_contexts)
- Modify: `generator/sources.py` (delete `load_reading`)
- Delete: `data/reading.yaml`
- Test: `tests/test_build.py` (rework reading fixtures and add three tests), `tests/test_sources.py` (delete two reading tests)

- [ ] **Step 1: Rework the test fixtures in `tests/test_build.py`**

Replace the `READING` constant and `_patch_sources` with:

```python
BOOKS = [
    {
        "title": "Book",
        "author": "Author",
        "url": "https://gr/b",
        "image_url": "https://img/c.jpg",
    }
]
COVER = {"url": "https://img/c.jpg", "b64": "QUJD", "mime": "image/jpeg"}


def _patch_sources(monkeypatch, writing=WRITING):
    monkeypatch.setattr(sources, "fetch_substack", lambda: writing)
    monkeypatch.setattr(sources, "fetch_activity", lambda token: SHIPPED)
    monkeypatch.setattr(sources, "load_talks", lambda path=None: TALKS)
    monkeypatch.setattr(sources, "fetch_goodreads", lambda: list(BOOKS))
    monkeypatch.setattr(build, "_download_cover", lambda url: dict(COVER))
```

- [ ] **Step 2: Add the failing tests**

Append to `tests/test_build.py`:

```python
def test_reading_tile_uses_goodreads_books(workspace, monkeypatch):
    _patch_sources(monkeypatch)
    assert build.main() == 0
    readme = build.README.read_text(encoding="utf-8")
    assert '<a href="https://gr/b">' in readme
    cache = json.loads(build.CACHE.read_text(encoding="utf-8"))
    assert cache["reading"]["books"] == BOOKS
    assert cache["reading"]["cover"]["url"] == "https://img/c.jpg"
    svg = (build.ASSETS / "reading-dark.svg").read_text(encoding="utf-8")
    assert "data:image/jpeg;base64,QUJD" in svg
    assert "via Goodreads" in svg


def test_cover_reuses_cache_when_url_unchanged(workspace, monkeypatch):
    _patch_sources(monkeypatch)
    assert build.main() == 0

    def explode(url):
        raise AssertionError("cover should not re-download on cache hit")

    _patch_sources(monkeypatch)
    monkeypatch.setattr(build, "_download_cover", explode)
    assert build.main() == 0
    svg = (build.ASSETS / "reading-dark.svg").read_text(encoding="utf-8")
    assert "data:image/jpeg;base64,QUJD" in svg


def test_cover_failure_renders_text_only(workspace, monkeypatch):
    _patch_sources(monkeypatch)
    monkeypatch.setattr(build, "_download_cover", lambda url: None)
    assert build.main() == 0
    svg = (build.ASSETS / "reading-dark.svg").read_text(encoding="utf-8")
    assert "<image" not in svg
    assert "Book" in svg


def test_old_yaml_cache_shape_treated_as_absent(workspace, monkeypatch):
    _patch_sources(monkeypatch)

    def boom():
        raise sources.SourceError("goodreads is down")

    monkeypatch.setattr(sources, "fetch_goodreads", boom)
    build.ASSETS.mkdir(parents=True, exist_ok=True)
    build.CACHE.write_text(
        json.dumps({"reading": {"title": "Old Book", "author": "X"}}),
        encoding="utf-8",
    )
    assert build.main() == 0
    svg = (build.ASSETS / "reading-dark.svg").read_text(encoding="utf-8")
    assert "Old Book" not in svg
```

Replace `test_tile_contexts_treats_incomplete_reading_as_missing` with:

```python
def test_tile_contexts_treats_missing_books_as_empty():
    tiles = build.tile_contexts({"reading": {"books": [], "cover": None}})
    reading = next(t for t in tiles if t["key"] == "reading")
    assert reading["lines"] == build.EMPTY_LINES
    assert reading["url"] == ""
```

In `tests/test_sources.py`, delete `test_load_reading_returns_current` and `test_load_reading_missing_author_raises`, and remove `load_reading` from the import block.

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `uv run --project generator pytest tests/test_build.py -v`
Expected: FAIL with `AttributeError: module 'generator.build' has no attribute '_download_cover'` (or fetch_goodreads patch errors)

- [ ] **Step 4: Implement the reading pipeline in `generator/build.py`**

Add `import base64` and `import httpx` to the imports.

Add the two functions above `gather`:

```python
def _download_cover(url: str) -> dict | None:
    try:
        resp = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": sources.USER_AGENT},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"warning: cover download failed: {exc}", file=sys.stderr)
        return None
    if len(resp.content) > COVER_MAX_BYTES:
        print("warning: cover exceeds size cap, skipping", file=sys.stderr)
        return None
    mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
    return {
        "url": url,
        "b64": base64.b64encode(resp.content).decode(),
        "mime": mime,
    }


def _resolve_reading(cache: dict) -> dict | None:
    """Fetch Goodreads books, reusing or downloading the first cover."""
    cached = cache.get("reading")
    if not isinstance(cached, dict) or "books" not in cached:
        cached = None
    try:
        books = sources.fetch_goodreads()
    except sources.SourceError as exc:
        print(f"warning: reading: {exc}; using last-good data", file=sys.stderr)
        return cached
    cover = None
    image_url = books[0].get("image_url") or ""
    cached_cover = (cached or {}).get("cover") or {}
    if image_url and cached_cover.get("url") == image_url and cached_cover.get("b64"):
        cover = cached_cover
    elif image_url:
        cover = _download_cover(image_url)
    fresh = {"books": books, "cover": cover}
    cache["reading"] = fresh
    return fresh
```

In `gather`, remove the `"reading"` entry from the `fetchers` dict and add one line right after the loop, before `cache["updated"] = today`:

```python
    data["reading"] = _resolve_reading(cache)
```

In `tile_contexts`, replace the whole reading section (the `raw_reading` block) with:

```python
    reading = data.get("reading")
    books = (reading or {}).get("books") or []
    if books:
        reading_lines = [
            {"primary": fit(b["title"], 84), "secondary": b["author"]}
            for b in books
        ]
    else:
        reading_lines = EMPTY_LINES
```

and replace the reading dict in the returned list with:

```python
        {
            "key": "reading",
            "header": "📚 READING NOW",
            "header_note": "via Goodreads" if books else "",
            "cover": (reading or {}).get("cover") if books else None,
            "lines": reading_lines,
            "url": books[0]["url"] if books else "",
            "alt": "Reading now: " + _summary(reading_lines),
        },
```

In `generator/sources.py`, delete the `load_reading` function entirely. Then delete the data file:

```bash
git rm data/reading.yaml
```

- [ ] **Step 5: Run the full suite**

Run: `uv run --project generator pytest tests/ -v`
Expected: 38 passed (36 minus 2 deleted reading-YAML tests, plus 4 new build tests, with the replaced tile test netting zero)

- [ ] **Step 6: Lint and format**

```bash
uv run --project generator ruff check generator tests
uv run --project generator ruff format --check generator tests
```

Expected: All checks passed, no reformat needed (run `ruff format` and re-test if it disagrees)

- [ ] **Step 7: Commit**

```bash
git add generator/build.py generator/sources.py tests/test_build.py tests/test_sources.py
git commit -m "Source the reading tile from Goodreads with embedded cover"
```

(The `git rm data/reading.yaml` from Step 4 is already staged and rides along in this commit.)

---

### Task 4: Real build, verification, push, and PR

**Files:**
- Modify: `README.md`, `assets/*` (regenerated by the build)

- [ ] **Step 1: Run the real build**

```bash
GITHUB_TOKEN=$(gh auth token) uv run --project generator python generator/build.py
```

Expected: `profile rebuilt` with no warnings (a warning means a source is genuinely down, investigate before continuing)

- [ ] **Step 2: Verify the output**

```bash
grep -c "…" assets/stage-dark.svg || echo "no ellipsis"
grep -o "Obviously Awesome[^<]*" assets/reading-dark.svg | head -1
grep -c "data:image/" assets/reading-dark.svg
grep -c 'width="100%"' README.md
```

Expected: `no ellipsis` (titles render whole), the full book title, `1` cover data URI, and a `width="100%"` line count of 5 (the hero img plus one img per tile).
If the ellipsis grep finds matches, inspect whether any live title legitimately exceeds 84 characters before treating it as a failure.

- [ ] **Step 3: Commit the regenerated profile**

```bash
git add README.md assets/
git commit -m "Rebuild profile with Goodreads reading row and vertical layout"
```

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/goodreads-vertical
gh pr create --title "Goodreads-powered reading row and vertical full-width layout" --body "$(cat <<'EOF'
## What this does

Two upgrades to the bento dashboard, per the approved spec
(docs/superpowers/specs/2026-06-11-goodreads-vertical-design.md).

1. The Reading Now row is now fully automated from Taylor's public
   Goodreads currently-reading shelf (RSS, no API key, no secrets),
   with the real book cover embedded as a base64 data URI and a
   via-Goodreads credit. data/reading.yaml is retired.
2. All four tiles become stacked full-width 1200px rows, raising title
   budgets from 40 to 84 characters. No more mid-word ellipses.

## Resilience

Same failure-isolation pattern as every other source. Goodreads outage
serves cached books and cover. Cover failures degrade to text-only.
Old-shape cache entries are ignored gracefully. Cover downloads are
capped at 80KB and reused from cache while the cover URL is unchanged.

## After merge

Nothing manual. The daily build keeps the shelf in sync. Update your
shelf on Goodreads and the profile follows within a day.
EOF
)"
```

Expected: PR URL printed

- [ ] **Step 5: Watch CI**

```bash
gh pr checks --watch
```

Expected: CI (pytest + ruff) and Lint both green. Fix any specific finding, commit, push, and re-watch.

- [ ] **Step 6: Stop for human visual QA**

Do not merge. Taylor reviews the rendered README on the PR branch in dark and light themes (tile proportions, cover rendering, truncation gone) and gives the merge call.

---

## Post-merge notes (for the human)

1. The next scheduled run exercises the full Goodreads path in production.
2. Updating the currently-reading shelf on Goodreads is now the only
   "content management" the reading row ever needs.
