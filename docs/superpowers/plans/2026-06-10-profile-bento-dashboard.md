# Profile Bento Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static profile README with a self-generating bento dashboard: custom SVG tiles (hero, writing, shipped, on-stage, reading, connect chips) rendered by a Python generator and refreshed daily by GitHub Actions.

**Architecture:** A small Python package (`generator/`) with three focused modules — `sources.py` (fetch/parse the four content sources), `render.py` (Jinja2 → SVG), `readme.py` (managed-region rewriting) — orchestrated by `build.py`. Generated SVGs and a last-good data cache are committed to `assets/`. Failure isolation: any dead source falls back to cached data so the profile never blanks. Spec: `docs/superpowers/specs/2026-06-10-profile-readme-design.md`.

**Tech Stack:** Python 3.12, uv, feedparser, httpx, PyYAML, Jinja2, pytest (golden-file tests), GitHub Actions.

**Working branch:** `feat/profile-bento-dashboard` (already created; spec is committed on it).

---

### Task 1: Scaffolding — gitignore, Python project, test harness

**Files:**
- Create: `.gitignore`
- Create: `generator/pyproject.toml`
- Create: `generator/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `conftest.py`

- [ ] **Step 1: Verify the action tags we will pin actually exist**

```bash
gh api repos/actions/checkout/tags --jq '.[].name' | head -5
gh api repos/astral-sh/setup-uv/tags --jq '.[].name' | head -5
gh api repos/super-linter/super-linter/tags --jq '.[].name' | grep -E '^v8\.6\.0$'
gh api repos/lycheeverse/lychee-action/tags --jq '.[].name' | grep -E '^v2\.8\.0$'
```

Expected: `v6.x.x` tags listed for checkout (the repo's existing workflows on main already use `@v6` and run green weekly), a `v6` tag for setup-uv, and exact matches for `v8.6.0` and `v2.8.0`. **If any tag is missing, use the newest tag that DOES exist and keep that choice consistent in Task 11.**

- [ ] **Step 2: Write `.gitignore`**

```gitignore
.superpowers/
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
.DS_Store
```

- [ ] **Step 3: Write `generator/pyproject.toml`**

```toml
[project]
name = "profile-generator"
version = "1.0.0"
description = "Generates the bento dashboard for onlydole/onlydole"
requires-python = ">=3.12"
dependencies = [
    "feedparser>=6.0",
    "httpx>=0.27",
    "PyYAML>=6.0",
    "Jinja2>=3.1",
]

[dependency-groups]
dev = ["pytest>=8.0"]
```

- [ ] **Step 4: Create empty `generator/__init__.py` and `tests/__init__.py`, and write `conftest.py`**

`conftest.py` (repo root):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 5: Sync the environment and verify pytest runs**

```bash
uv sync --project generator
uv run --project generator pytest tests/ -v
```

Expected: lockfile `generator/uv.lock` created; pytest reports `no tests ran` (exit code 5 is fine at this stage).

- [ ] **Step 6: Commit**

```bash
git add .gitignore generator/pyproject.toml generator/uv.lock generator/__init__.py tests/__init__.py conftest.py
git commit -m "Add generator scaffolding and test harness"
```

---

### Task 2: Seed data files (real content)

**Files:**
- Create: `data/talks.yaml`
- Create: `data/reading.yaml`

- [ ] **Step 1: Write `data/talks.yaml`** (verified real entries, researched 2026-06-10 from onlydole.dev/talks, kube.fm, and YouTube)

```yaml
# Append an entry when you give a talk / join a podcast. The newest 3 show
# on the profile. Required: title, venue, date, url. Optional: kind.
- title: "The Missing Manual for Open Source Community Sustainability"
  venue: "KubeCon + CloudNativeCon NA, Atlanta"
  date: 2025-11-11
  url: "https://kccncna2025.sched.com/event/51807c07f8572b3211e24e9430ec6f26"
  kind: talk

- title: "Navigating Contributions and Community Health in Kubernetes"
  venue: "KubeFM podcast"
  date: 2025-11-03
  url: "https://kube.fm/navigating-contributions-community-taylor"
  kind: podcast

- title: "Keynote: Above the Clouds — Mountainous Achievements with End Users"
  venue: "KubeCon + CloudNativeCon NA, Salt Lake City"
  date: 2024-11-15
  url: "https://www.youtube.com/watch?v=TnYupUh6OIg"
  kind: keynote
```

- [ ] **Step 2: Write `data/reading.yaml`** (seeded from the design mockups — **Taylor: edit this to your actual current book**)

```yaml
# Edit when you pick up a new book. url and note are optional.
current:
  title: "Thinking in Systems"
  author: "Donella Meadows"
  url: ""
  note: "A primer on seeing wholes — systems thinking for everything."
```

- [ ] **Step 3: Validate both parse as YAML**

```bash
uv run --project generator python -c "import yaml,pathlib; [yaml.safe_load(pathlib.Path(p).read_text()) for p in ('data/talks.yaml','data/reading.yaml')]; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add data/talks.yaml data/reading.yaml
git commit -m "Seed talks and reading data files"
```

---

### Task 3: README managed-region rewriting (`generator/readme.py`)

**Files:**
- Create: `generator/readme.py`
- Test: `tests/test_readme.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_readme.py`:

```python
import pytest

from generator.readme import MarkerError, replace_region

DOC = "intro\n<!-- bento:start -->old stuff<!-- bento:end -->\nfooter\n"


def test_replace_region_swaps_body():
    out = replace_region(DOC, "bento", "NEW")
    assert "<!-- bento:start -->NEW<!-- bento:end -->" in out
    assert "old stuff" not in out
    assert out.startswith("intro\n")
    assert out.endswith("footer\n")


def test_replace_region_handles_multiline_body():
    out = replace_region(DOC, "bento", "\nline1\nline2\n")
    assert "<!-- bento:start -->\nline1\nline2\n<!-- bento:end -->" in out


def test_replace_region_missing_markers_raises():
    with pytest.raises(MarkerError):
        replace_region("no markers here", "bento", "NEW")


def test_replace_region_body_with_regex_specials():
    out = replace_region(DOC, "bento", r"path\1 and \g<0> and $&")
    assert r"path\1 and \g<0> and $&" in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project generator pytest tests/test_readme.py -v
```

Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'generator.readme'`

- [ ] **Step 3: Write the implementation**

`generator/readme.py`:

```python
"""Rewrite managed regions of README.md between HTML comment markers."""

import re


class MarkerError(ValueError):
    """Raised when a managed region's markers are missing."""


def replace_region(content: str, name: str, new_body: str) -> str:
    """Replace text between <!-- name:start --> and <!-- name:end -->.

    Markers are preserved. new_body is inserted literally (no regex
    backreference expansion). Raises MarkerError if markers are absent.
    """
    start = f"<!-- {name}:start -->"
    end = f"<!-- {name}:end -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(content):
        raise MarkerError(f"markers for region {name!r} not found")
    return pattern.sub(lambda _m: start + new_body + end, content)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project generator pytest tests/test_readme.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add generator/readme.py tests/test_readme.py
git commit -m "Add README managed-region rewriting"
```

---

### Task 4: Text fitting + render module core (`generator/render.py`)

**Files:**
- Create: `generator/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:

```python
from generator.render import fit


def test_fit_short_text_unchanged():
    assert fit("hello", 10) == "hello"


def test_fit_truncates_with_ellipsis():
    assert fit("a long title here", 8) == "a long…"


def test_fit_exact_length_unchanged():
    assert fit("12345678", 8) == "12345678"


def test_fit_collapses_internal_whitespace():
    assert fit("a\n  b\tc", 20) == "a b c"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project generator pytest tests/test_render.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'generator.render'`

- [ ] **Step 3: Write the implementation**

`generator/render.py`:

```python
"""Render SVG assets from Jinja2 templates."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / "templates"

DARK = {
    "bg": "#1a1417",
    "border": "#463038",
    "accent": "#ff9d76",
    "text": "#e6ddd9",
    "muted": "#a08a84",
}
LIGHT = {
    "bg": "#fff6f0",
    "border": "#f3ddd0",
    "accent": "#c2414f",
    "text": "#44322e",
    "muted": "#8a6f66",
}
FONT_STACK = "-apple-system, 'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif"


def fit(text: str, max_chars: int) -> str:
    """Collapse whitespace and truncate to max_chars with an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def render_svg(template_name: str, context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        keep_trailing_newline=True,
    )
    return env.get_template(template_name).render(**context)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project generator pytest tests/test_render.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add generator/render.py tests/test_render.py
git commit -m "Add SVG render module with text fitting"
```

---

### Task 5: SVG templates + golden-file tests

**Files:**
- Create: `generator/templates/hero.svg.j2`
- Create: `generator/templates/tile.svg.j2`
- Create: `generator/templates/chip.svg.j2`
- Create: `tests/golden_cases.py`
- Create: `tests/update_goldens.py`
- Create: `tests/goldens/` (generated `.svg` files, committed)
- Test: append to `tests/test_render.py`

- [ ] **Step 1: Write the shared golden cases**

`tests/golden_cases.py`:

```python
"""Fixture contexts shared by the golden test and the regenerator."""

from generator.render import DARK, FONT_STACK, LIGHT

CASES = {
    "hero.svg": (
        "hero.svg.j2",
        {
            "font": FONT_STACK,
            "aria": "Taylor Dolezal — Head of Open Source at Dosu · "
                    "CNCF Ambassador · Los Angeles",
            "name": "Taylor Dolezal",
            "role": "Head of Open Source @ Dosu · CNCF Ambassador · Los Angeles",
            "cred": "KubeCon keynoter · ex-Disney Studios SRE · ex-HashiCorp",
        },
    ),
    "tile-writing-dark.svg": (
        "tile.svg.j2",
        {
            "font": FONT_STACK,
            "theme": DARK,
            "header": "✍️ LATEST WRITING",
            "aria": "Latest writing: Fixture post (2026-01-02)",
            "lines": [
                {"primary": "Fixture post", "secondary": "2026-01-02"},
                {"primary": "Second post with <angle> & amp", "secondary": "2026-01-01"},
            ],
        },
    ),
    "tile-writing-light.svg": (
        "tile.svg.j2",
        {
            "font": FONT_STACK,
            "theme": LIGHT,
            "header": "✍️ LATEST WRITING",
            "aria": "Latest writing: Fixture post (2026-01-02)",
            "lines": [{"primary": "Fixture post", "secondary": "2026-01-02"}],
        },
    ),
    "chip-substack-dark.svg": (
        "chip.svg.j2",
        {"font": FONT_STACK, "theme": DARK, "label": "Substack"},
    ),
}
```

- [ ] **Step 2: Append the failing golden test to `tests/test_render.py`**

```python
from pathlib import Path

from generator.render import render_svg
from tests.golden_cases import CASES

GOLDENS = Path(__file__).parent / "goldens"


def test_rendered_svgs_match_goldens():
    for name, (template, context) in CASES.items():
        golden = GOLDENS / name
        assert golden.exists(), f"missing golden {name}; run tests/update_goldens.py"
        assert render_svg(template, context) == golden.read_text(encoding="utf-8"), name


def test_svg_output_escapes_xml():
    _, context = CASES["tile-writing-dark.svg"]
    svg = render_svg("tile.svg.j2", context)
    assert "&lt;angle&gt; &amp; amp" in svg
    assert "<angle>" not in svg
```

(Add the imports at the top of the file with the existing `fit` import.)

- [ ] **Step 3: Run tests to verify the golden test fails**

```bash
uv run --project generator pytest tests/test_render.py -v
```

Expected: FAIL — `TemplateNotFound` or missing-golden assertion.

- [ ] **Step 4: Write the three templates**

`generator/templates/hero.svg.j2`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 300" role="img" aria-label="{{ aria }}">
  <defs>
    <linearGradient id="sunset" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#7c2d4f"/>
      <stop offset="55%" stop-color="#c2414f"/>
      <stop offset="100%" stop-color="#e8702a"/>
    </linearGradient>
    <linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="50%" stop-color="#ffffff" stop-opacity="0.10"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="frame">
      <rect width="1200" height="300" rx="18"/>
    </clipPath>
  </defs>
  <rect width="1200" height="300" rx="18" fill="url(#sunset)"/>
  <g clip-path="url(#frame)">
    <rect x="-600" y="-40" width="420" height="380" fill="url(#sheen)" transform="skewX(-18)">
      <animate attributeName="x" values="-600;1560" dur="9s" repeatCount="indefinite"/>
    </rect>
  </g>
  <text x="64" y="132" font-family="{{ font }}" font-size="58" font-weight="700" fill="#ffffff">{{ name }}</text>
  <text x="64" y="184" font-family="{{ font }}" font-size="25" fill="#ffe8dd">{{ role }}</text>
  <text x="64" y="228" font-family="{{ font }}" font-size="19" fill="#ffd2bd" opacity="0.9">{{ cred }}</text>
</svg>
```

`generator/templates/tile.svg.j2`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 340" role="img" aria-label="{{ aria }}">
  <rect x="1.5" y="1.5" width="597" height="337" rx="16" fill="{{ theme.bg }}" stroke="{{ theme.border }}" stroke-width="2"/>
  <text x="36" y="62" font-family="{{ font }}" font-size="22" font-weight="700" letter-spacing="2.5" fill="{{ theme.accent }}">{{ header }}</text>
{% for line in lines %}
  <text x="36" y="{{ 122 + loop.index0 * 74 }}" font-family="{{ font }}" font-size="25" fill="{{ theme.text }}">{{ line.primary }}</text>
  <text x="36" y="{{ 152 + loop.index0 * 74 }}" font-family="{{ font }}" font-size="17" fill="{{ theme.muted }}">{{ line.secondary }}</text>
{% endfor %}
</svg>
```

`generator/templates/chip.svg.j2`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 46" role="img" aria-label="{{ label }}">
  <rect x="1" y="1" width="198" height="44" rx="22" fill="{{ theme.bg }}" stroke="{{ theme.border }}" stroke-width="2"/>
  <text x="100" y="29" text-anchor="middle" font-family="{{ font }}" font-size="18" font-weight="600" fill="{{ theme.accent }}">{{ label }} ↗</text>
</svg>
```

- [ ] **Step 5: Write the golden regenerator**

`tests/update_goldens.py`:

```python
"""Regenerate golden SVGs. Run from repo root:
uv run --project generator python tests/update_goldens.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.render import render_svg          # noqa: E402
from tests.golden_cases import CASES             # noqa: E402

GOLDENS = Path(__file__).parent / "goldens"

if __name__ == "__main__":
    GOLDENS.mkdir(exist_ok=True)
    for name, (template, context) in CASES.items():
        (GOLDENS / name).write_text(render_svg(template, context), encoding="utf-8")
        print(f"wrote {name}")
```

- [ ] **Step 6: Generate goldens, eyeball them, run tests**

```bash
uv run --project generator python tests/update_goldens.py
open tests/goldens/hero.svg tests/goldens/tile-writing-dark.svg
uv run --project generator pytest tests/test_render.py -v
```

Expected: 4 golden files written; SVGs open in browser and look like the approved mockups (sunset gradient hero with slow sheen sweep, warm dark tile); all tests pass.

- [ ] **Step 7: Commit**

```bash
git add generator/templates/ tests/golden_cases.py tests/update_goldens.py tests/goldens/ tests/test_render.py
git commit -m "Add SVG templates with golden-file tests"
```

---

### Task 6: Substack source (`generator/sources.py`, part 1)

**Files:**
- Create: `generator/sources.py`
- Create: `tests/fixtures/substack.xml`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Write the RSS fixture**

`tests/fixtures/substack.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Taylor's Substack</title>
    <item>
      <title>Newest fixture post</title>
      <link>https://onlydole.substack.com/p/newest</link>
      <pubDate>Mon, 08 Jun 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Middle fixture post</title>
      <link>https://onlydole.substack.com/p/middle</link>
      <pubDate>Mon, 01 Jun 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Oldest fixture post</title>
      <link>https://onlydole.substack.com/p/oldest</link>
      <pubDate>Sun, 24 May 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Fourth post beyond the cap</title>
      <link>https://onlydole.substack.com/p/fourth</link>
      <pubDate>Sun, 17 May 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: Write the failing tests**

`tests/test_sources.py`:

```python
from pathlib import Path

import pytest

from generator.sources import SourceError, parse_substack

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
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run --project generator pytest tests/test_sources.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'generator.sources'`

- [ ] **Step 4: Write `generator/sources.py` with the Substack functions**

```python
"""Fetch and parse the four content sources."""

from __future__ import annotations

import datetime
from pathlib import Path

import feedparser
import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBSTACK_FEED = "https://onlydole.substack.com/feed"
GITHUB_LOGIN = "onlydole"
PROFILE_REPO = "onlydole/onlydole"
GRAPHQL_URL = "https://api.github.com/graphql"


class SourceError(RuntimeError):
    """A content source could not be fetched or parsed."""


def parse_substack(feed_text: str) -> list[dict]:
    parsed = feedparser.parse(feed_text)
    if parsed.bozo and not parsed.entries:
        raise SourceError(f"unparseable feed: {parsed.bozo_exception}")
    posts = []
    for entry in parsed.entries[:3]:
        published = entry.get("published_parsed")
        if not (entry.get("title") and entry.get("link") and published):
            continue
        posts.append(
            {
                "title": entry["title"],
                "url": entry["link"],
                "date": datetime.date(*published[:3]).isoformat(),
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run --project generator pytest tests/test_sources.py -v
```

Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add generator/sources.py tests/fixtures/substack.xml tests/test_sources.py
git commit -m "Add Substack feed source with fixture tests"
```

---

### Task 7: GitHub activity source (`generator/sources.py`, part 2)

**Files:**
- Modify: `generator/sources.py` (append)
- Create: `tests/fixtures/activity.json`
- Test: `tests/test_sources.py` (append)

- [ ] **Step 1: Write the GraphQL response fixture**

`tests/fixtures/activity.json`:

```json
{
  "data": {
    "user": {
      "repositories": {
        "nodes": [
          {
            "name": "demo-repo",
            "url": "https://github.com/onlydole/demo-repo",
            "releases": {
              "nodes": [
                {
                  "tagName": "v1.2.0",
                  "publishedAt": "2026-06-05T10:00:00Z",
                  "url": "https://github.com/onlydole/demo-repo/releases/tag/v1.2.0"
                }
              ]
            }
          },
          {
            "name": "older-repo",
            "url": "https://github.com/onlydole/older-repo",
            "releases": {
              "nodes": [
                {
                  "tagName": "v0.3.0",
                  "publishedAt": "2026-05-30T10:00:00Z",
                  "url": "https://github.com/onlydole/older-repo/releases/tag/v0.3.0"
                }
              ]
            }
          },
          {
            "name": "no-releases",
            "url": "https://github.com/onlydole/no-releases",
            "releases": { "nodes": [] }
          }
        ]
      },
      "pullRequests": {
        "nodes": [
          {
            "title": "Fix scheduler docs",
            "url": "https://github.com/kubernetes/website/pull/999",
            "mergedAt": "2026-06-07T10:00:00Z",
            "repository": { "nameWithOwner": "kubernetes/website", "isPrivate": false }
          },
          {
            "title": "Secret work",
            "url": "https://github.com/private/repo/pull/1",
            "mergedAt": "2026-06-08T10:00:00Z",
            "repository": { "nameWithOwner": "private/repo", "isPrivate": true }
          },
          {
            "title": "Profile tweak",
            "url": "https://github.com/onlydole/onlydole/pull/35",
            "mergedAt": "2026-06-06T10:00:00Z",
            "repository": { "nameWithOwner": "onlydole/onlydole", "isPrivate": false }
          }
        ]
      }
    }
  }
}
```

- [ ] **Step 2: Append the failing tests to `tests/test_sources.py`**

```python
import json

from generator.sources import parse_activity


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
```

(`json` import goes at the top of the file with the others.)

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run --project generator pytest tests/test_sources.py -v
```

Expected: FAIL with `ImportError: cannot import name 'parse_activity'`

- [ ] **Step 4: Append to `generator/sources.py`**

```python
ACTIVITY_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 50, privacy: PUBLIC, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        url
        releases(first: 1, orderBy: {field: CREATED_AT, direction: DESC}) {
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
        repo = pr["repository"]
        if repo["isPrivate"] or repo["nameWithOwner"] == PROFILE_REPO:
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run --project generator pytest tests/test_sources.py -v
```

Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add generator/sources.py tests/fixtures/activity.json tests/test_sources.py
git commit -m "Add GitHub activity source via GraphQL"
```

---

### Task 8: Talks and reading sources (`generator/sources.py`, part 3)

**Files:**
- Modify: `generator/sources.py` (append)
- Test: `tests/test_sources.py` (append)

- [ ] **Step 1: Append the failing tests to `tests/test_sources.py`**

```python
from generator.sources import load_reading, load_talks


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
    assert book == {"title": "Book", "author": "Author", "url": "", "note": "Why I like it"}


def test_load_reading_missing_author_raises(tmp_path):
    reading = tmp_path / "reading.yaml"
    reading.write_text('current: {title: "Book"}', encoding="utf-8")
    with pytest.raises(SourceError):
        load_reading(reading)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project generator pytest tests/test_sources.py -v
```

Expected: FAIL with `ImportError: cannot import name 'load_reading'`

- [ ] **Step 3: Append to `generator/sources.py`**

```python
def load_talks(path: Path | None = None) -> list[dict]:
    path = path or REPO_ROOT / "data" / "talks.yaml"
    entries = _load_yaml(path)
    if not isinstance(entries, list) or not entries:
        raise SourceError("talks.yaml must be a non-empty list")
    for entry in entries:
        for field in ("title", "venue", "date", "url"):
            if not entry.get(field):
                raise SourceError(f"talks.yaml entry missing {field!r}")
    entries.sort(key=lambda e: str(e["date"]), reverse=True)
    return [
        {
            "title": e["title"],
            "venue": e["venue"],
            "date": str(e["date"]),
            "url": e["url"],
            "kind": e.get("kind", "talk"),
        }
        for e in entries[:3]
    ]


def load_reading(path: Path | None = None) -> dict:
    path = path or REPO_ROOT / "data" / "reading.yaml"
    data = _load_yaml(path)
    current = (data or {}).get("current") or {}
    if not (current.get("title") and current.get("author")):
        raise SourceError("reading.yaml needs current.title and current.author")
    return {
        "title": current["title"],
        "author": current["author"],
        "url": current.get("url") or "",
        "note": current.get("note") or "",
    }


def _load_yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SourceError(f"{path.name}: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project generator pytest tests/test_sources.py -v
```

Expected: 9 passed

- [ ] **Step 5: Sanity-check against the real data files**

```bash
uv run --project generator python -c "from generator.sources import load_talks, load_reading; print(load_talks()[0]['title']); print(load_reading()['title'])"
```

Expected: `The Missing Manual for Open Source Community Sustainability` then `Thinking in Systems`

- [ ] **Step 6: Commit**

```bash
git add generator/sources.py tests/test_sources.py
git commit -m "Add talks and reading YAML sources"
```

---

### Task 9: Build orchestration (`generator/build.py`)

**Files:**
- Create: `generator/build.py`
- Test: `tests/test_build.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_build.py`:

```python
import json

import pytest

from generator import build, sources

README_FRAME = (
    "<!-- bento:start --><!-- bento:end -->\n"
    "prose stays\n"
    "<sub><!-- stamp:start --><!-- stamp:end --></sub>\n"
)

WRITING = [{"title": "Post", "url": "https://s/p", "date": "2026-06-08"}]
SHIPPED = [{"title": "repo v1", "detail": "release", "url": "https://g/r", "date": "2026-06-05"}]
TALKS = [{"title": "Talk", "venue": "Conf", "date": "2026-04-01", "url": "https://t/1", "kind": "talk"}]
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
        "writing-dark.svg", "writing-light.svg",
        "shipped-dark.svg", "shipped-light.svg",
        "stage-dark.svg", "stage-light.svg",
        "reading-dark.svg", "reading-light.svg",
        "chip-substack-dark.svg", "chip-website-light.svg",
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
    assert '<a href="https://s/p">' in second          # cached writing link survives
    assert "Last refreshed: 2026-06-11" in second      # stamp still advanced


def test_dead_source_with_no_cache_renders_empty_state(workspace, monkeypatch):
    _patch_sources(monkeypatch)

    def boom():
        raise sources.SourceError("substack is down")

    monkeypatch.setattr(sources, "fetch_substack", boom)
    assert build.main() == 0
    readme = build.README.read_text(encoding="utf-8")
    assert '<a href="https://onlydole.substack.com">' in readme  # fallback link
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --project generator pytest tests/test_build.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'generator.build'`

- [ ] **Step 3: Write `generator/build.py`**

```python
"""Build the bento dashboard: fetch sources, render SVGs, rewrite README."""

from __future__ import annotations

import datetime
import html
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import sources
from generator.readme import replace_region
from generator.render import DARK, FONT_STACK, LIGHT, fit, render_svg

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "assets"
CACHE = ASSETS / "data-cache.json"
README = REPO_ROOT / "README.md"

SITE = "https://onlydole.dev"
SUBSTACK_HOME = "https://onlydole.substack.com"
CHIPS = [
    ("substack", "Substack", SUBSTACK_HOME),
    ("linkedin", "LinkedIn", "https://www.linkedin.com/in/onlydole"),
    ("bluesky", "Bluesky", "https://bsky.app/profile/onlydole.dev"),
    ("website", "Website", SITE),
]
HERO = {
    "name": "Taylor Dolezal",
    "role": "Head of Open Source @ Dosu · CNCF Ambassador · Los Angeles",
    "cred": "KubeCon keynoter · ex-Disney Studios SRE · ex-HashiCorp",
}
HERO_ALT = (
    "Taylor Dolezal — Head of Open Source at Dosu · CNCF Ambassador · Los Angeles"
)
EMPTY_LINES = [{"primary": "—", "secondary": ""}]


def gather(today: str) -> dict:
    """Fetch every source; fall back to last-good cache on failure."""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    fetchers = {
        "writing": lambda: sources.fetch_substack(),
        "shipped": lambda: sources.fetch_activity(os.environ["GITHUB_TOKEN"]),
        "stage": lambda: sources.load_talks(),
        "reading": lambda: sources.load_reading(),
    }
    data = {}
    for key, fetch in fetchers.items():
        try:
            data[key] = fetch()
            cache[key] = data[key]
        except (sources.SourceError, KeyError) as exc:
            print(f"warning: {key}: {exc}; using last-good data", file=sys.stderr)
            data[key] = cache.get(key)
    cache["updated"] = today
    ASSETS.mkdir(exist_ok=True)
    CACHE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return data


def _summary(lines: list[dict]) -> str:
    parts = []
    for line in lines:
        if line["secondary"]:
            parts.append(f"{line['primary']} ({line['secondary']})")
        elif line["primary"]:
            parts.append(line["primary"])
    return "; ".join(parts) or "no items"


def tile_contexts(data: dict) -> list[dict]:
    writing = data.get("writing")
    writing_lines = (
        [{"primary": fit(p["title"], 40), "secondary": p["date"]} for p in writing]
        if writing
        else EMPTY_LINES
    )

    shipped = data.get("shipped")
    shipped_lines = (
        [
            {"primary": fit(i["title"], 40), "secondary": f"{i['detail']} · {i['date']}"}
            for i in shipped
        ]
        if shipped
        else EMPTY_LINES
    )

    stage = data.get("stage")
    stage_lines = (
        [
            {"primary": fit(t["title"], 40), "secondary": fit(f"{t['venue']} · {t['date']}", 52)}
            for t in stage
        ]
        if stage
        else EMPTY_LINES
    )

    reading = data.get("reading")
    if reading:
        reading_lines = [
            {"primary": fit(reading["title"], 38), "secondary": reading["author"]}
        ]
        if reading["note"]:
            reading_lines.append({"primary": "", "secondary": fit(reading["note"], 60)})
    else:
        reading_lines = EMPTY_LINES

    return [
        {
            "key": "writing",
            "header": "✍️ LATEST WRITING",
            "lines": writing_lines,
            "url": writing[0]["url"] if writing else SUBSTACK_HOME,
            "alt": "Latest writing: " + _summary(writing_lines),
        },
        {
            "key": "shipped",
            "header": "🔨 RECENTLY SHIPPED",
            "lines": shipped_lines,
            "url": shipped[0]["url"] if shipped else f"https://github.com/{sources.GITHUB_LOGIN}",
            "alt": "Recently shipped: " + _summary(shipped_lines),
        },
        {
            "key": "stage",
            "header": "🎤 ON STAGE",
            "lines": stage_lines,
            "url": stage[0]["url"] if stage else SITE,
            "alt": "On stage: " + _summary(stage_lines),
        },
        {
            "key": "reading",
            "header": "📚 READING NOW",
            "lines": reading_lines,
            "url": reading["url"] if reading else "",
            "alt": "Reading now: " + _summary(reading_lines),
        },
    ]


def write_assets(tiles: list[dict]) -> None:
    ASSETS.mkdir(exist_ok=True)
    hero_ctx = {"font": FONT_STACK, "aria": HERO_ALT, **HERO}
    (ASSETS / "hero.svg").write_text(
        render_svg("hero.svg.j2", hero_ctx), encoding="utf-8"
    )
    themes = (("dark", DARK), ("light", LIGHT))
    for tile in tiles:
        for theme_name, theme in themes:
            svg = render_svg(
                "tile.svg.j2",
                {
                    "font": FONT_STACK,
                    "theme": theme,
                    "header": tile["header"],
                    "lines": tile["lines"],
                    "aria": tile["alt"],
                },
            )
            (ASSETS / f"{tile['key']}-{theme_name}.svg").write_text(
                svg, encoding="utf-8"
            )
    for key, label, _url in CHIPS:
        for theme_name, theme in themes:
            svg = render_svg(
                "chip.svg.j2", {"font": FONT_STACK, "theme": theme, "label": label}
            )
            (ASSETS / f"chip-{key}-{theme_name}.svg").write_text(svg, encoding="utf-8")


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _picture(key: str, alt: str, width: str) -> str:
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" '
        f'srcset="assets/{key}-dark.svg">'
        f'<img src="assets/{key}-light.svg" width="{width}" alt="{_esc(alt)}">'
        f"</picture>"
    )


def bento_html(tiles: list[dict]) -> str:
    rows = [
        f'<a href="{SITE}"><img src="assets/hero.svg" width="100%" '
        f'alt="{_esc(HERO_ALT)}"></a>'
    ]
    for pair in (tiles[0:2], tiles[2:4]):
        cells = []
        for tile in pair:
            picture = _picture(tile["key"], tile["alt"], "49%")
            if tile["url"]:
                cells.append(f'<a href="{_esc(tile["url"])}">{picture}</a>')
            else:
                cells.append(picture)
        rows.append('<p align="center">\n  ' + "\n  ".join(cells) + "\n</p>")
    chips = [
        f'<a href="{_esc(url)}">{_picture("chip-" + key, label, "150")}</a>'
        for key, label, url in CHIPS
    ]
    rows.append('<p align="center">\n  ' + "\n  ".join(chips) + "\n</p>")
    return "\n".join(rows)


def main() -> int:
    today = os.environ.get("BUILD_DATE") or datetime.date.today().isoformat()
    data = gather(today)
    tiles = tile_contexts(data)
    write_assets(tiles)
    content = README.read_text(encoding="utf-8")
    content = replace_region(content, "bento", "\n" + bento_html(tiles) + "\n")
    content = replace_region(content, "stamp", f"Last refreshed: {today}")
    README.write_text(content, encoding="utf-8")
    print("profile rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --project generator pytest tests/test_build.py -v
```

Expected: 3 passed

- [ ] **Step 5: Run the whole suite**

```bash
uv run --project generator pytest tests/ -v
```

Expected: 22 passed

- [ ] **Step 6: Commit**

```bash
git add generator/build.py tests/test_build.py
git commit -m "Add build orchestration with cache fallback"
```

---

### Task 10: New README frame + first real build

**Files:**
- Modify: `README.md` (full replacement)
- Create: `assets/*.svg`, `assets/data-cache.json` (generated)

- [ ] **Step 1: Replace `README.md` with the static frame**

```markdown
<!-- The block below is generated by generator/build.py — edit the prose
     after it, never the generated block itself. -->
<!-- bento:start -->
<!-- bento:end -->

## A little more about me

I've spent my career refactoring complex systems into intuitive platforms —
running production at Disney Studios, developer advocacy at HashiCorp,
stewarding the end-user ecosystem at CNCF, and now leading open source at
[Dosu](https://dosu.dev). I care about the humans behind the code:
maintainers, newcomers, and the communities that keep this ecosystem
thriving. Reach out about Kubernetes, AI infrastructure, open source — or
the best hikes in LA.

<sub>⚡ <!-- stamp:start --><!-- stamp:end --> · rebuilt daily by
[GitHub Actions](.github/workflows/build-profile.yml) ·
[how it works](generator/)</sub>
```

- [ ] **Step 2: Run the real build locally**

```bash
GITHUB_TOKEN=$(gh auth token) uv run --project generator python generator/build.py
```

Expected: `profile rebuilt` (a `warning: …; using last-good data` line for a source is acceptable ONLY if that source is genuinely down — investigate any warning before continuing).

- [ ] **Step 3: Inspect the output**

```bash
ls assets/
open assets/hero.svg assets/writing-dark.svg assets/writing-light.svg
head -40 README.md
```

Expected: 17 generated SVGs + `data-cache.json`; hero shows the sunset gradient with the name/role/credibility lines and a slow sheen sweep; writing tile lists real Substack posts (dark and light variants); README's bento region is populated and the stamp shows today's date.

- [ ] **Step 4: Commit**

```bash
git add README.md assets/
git commit -m "Replace README with generated bento dashboard"
```

---

### Task 11: Workflows and lint configuration

**Files:**
- Create: `.github/workflows/build-profile.yml`
- Create: `.github/workflows/ci.yml`
- Create: `.github/linters/.markdownlint.yaml`
- Modify: `.github/workflows/superlinter.yml`
- Modify: `.github/workflows/linkchecker.yml`
- Modify: `lychee.toml`

Use the action versions verified in Task 1 Step 1 everywhere below.

- [ ] **Step 1: Write `.github/workflows/build-profile.yml`**

```yaml
---
name: Build profile

on:
  schedule:
    - cron: "17 8 * * *"
  workflow_dispatch:
  push:
    branches:
      - main
    paths:
      - "data/**"
      - "generator/**"

permissions:
  contents: write

concurrency:
  group: build-profile

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: astral-sh/setup-uv@v6

      - name: Rebuild dashboard
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: uv run --project generator python generator/build.py

      - name: Commit and push if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add README.md assets/
          git diff --cached --quiet || git commit -m "chore: refresh profile dashboard"
          git push
```

(Note: the bot only touches `README.md` and `assets/`, which are outside the `push` path filter, and `GITHUB_TOKEN` pushes never re-trigger workflows — no loop is possible.)

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

```yaml
---
name: CI

on:
  pull_request:
    branches:
      - main

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: astral-sh/setup-uv@v6

      - name: Run tests
        run: uv run --project generator pytest tests/ -v

      - name: Lint generator
        run: uvx ruff check generator tests
```

- [ ] **Step 3: Write `.github/linters/.markdownlint.yaml`**

```yaml
---
# Relaxed rules for a rich profile README (inline HTML + generated content).
default: true
MD013: false  # line length — long URLs and HTML embeds
MD033: false  # inline HTML — required for <picture>/<img> layout
MD034: false  # bare URLs — appear in HTML comments
MD041: false  # first line need not be a heading — README opens with the hero
```

- [ ] **Step 4: Update `.github/workflows/superlinter.yml`** — bump the pin and point at the new config. Replace the `Super-linter` step with:

```yaml
      - name: Super-linter
        uses: super-linter/super-linter@v8.6.0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          VALIDATE_GITHUB_ACTIONS_ZIZMOR: false
          MARKDOWN_CONFIG_FILE: .markdownlint.yaml
          FILTER_REGEX_EXCLUDE: (assets/|tests/goldens/|tests/fixtures/|docs/superpowers/)
          VALIDATE_PYTHON_PYLINT: false
          VALIDATE_PYTHON_MYPY: false
          VALIDATE_PYTHON_ISORT: false
          VALIDATE_PYTHON_BLACK: false
          VALIDATE_PYTHON_FLAKE8: false
          VALIDATE_JSCPD: false
```

(Python linting is ruff's job in `ci.yml`; super-linter's overlapping Python linters are disabled to avoid double-mastering.)

- [ ] **Step 5: Update `.github/workflows/linkchecker.yml`** — change the lychee pin:

```yaml
        uses: lycheeverse/lychee-action@v2.8.0
```

- [ ] **Step 6: Replace `lychee.toml`**

```toml
# Substack and LinkedIn block automated checkers; badge-style hosts rate-limit.
exclude = [
  '.*substack\.com.*',
  '.*linkedin\.com.*',
]

# Accept success, 403 (bot-blocked but alive), and 429 (rate-limited).
accept = ["200..=299", "403", "429"]
```

- [ ] **Step 7: Validate workflow YAML and lint the Python**

```bash
uv run --project generator python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/**/*.y*ml', recursive=True)]; print('yaml ok')"
uvx ruff check generator tests
```

Expected: `yaml ok` and `All checks passed!`

- [ ] **Step 8: Commit**

```bash
git add .github/ lychee.toml
git commit -m "Add build and CI workflows, update linter configuration"
```

---

### Task 12: Full verification, push, and PR

- [ ] **Step 1: Run the entire test suite one final time**

```bash
uv run --project generator pytest tests/ -v
```

Expected: 22 passed, 0 failed.

- [ ] **Step 2: Re-run the real build to confirm idempotency**

```bash
GITHUB_TOKEN=$(gh auth token) uv run --project generator python generator/build.py
git status --short
```

Expected: `profile rebuilt`; git status shows no changes (same data → same output) or only `assets/data-cache.json` if a source updated between runs.

- [ ] **Step 3: Push the branch and open the PR**

```bash
git push -u origin feat/profile-bento-dashboard
gh pr create --title "Rebuild profile as a self-updating bento dashboard" --body "$(cat <<'EOF'
## What this does

Replaces the static profile README with a living dashboard: custom SVG bento
tiles (hero, latest writing, recently shipped, on stage, reading now, connect
chips) generated by a small Python tool and refreshed daily by GitHub Actions.
Zero third-party widget services — everything renders from this repo.

Design spec: docs/superpowers/specs/2026-06-10-profile-readme-design.md

## Highlights

- LA Sunset hero with subtle sheen animation, dark/light tile variants via <picture>
- Per-source failure isolation: a dead feed falls back to cached content, never blanks
- Golden-file tests lock the SVG output; ruff + pytest run in CI
- Supersedes closed PRs #33/#34 (action pins bumped) and #35 (rethought from scratch)

## After merge (one-time)

1. Actions → "Build profile" → Run workflow (or wait for the daily 08:17 UTC run)
2. Update data/reading.yaml to your actual current book
3. Append future talks to data/talks.yaml — the profile picks them up automatically
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 4: Watch CI**

```bash
gh pr checks --watch
```

Expected: CI (pytest + ruff), Lint (super-linter) all green. If super-linter flags something, fix the specific finding and push.

- [ ] **Step 5: Visual QA (human step — Taylor)**

Open the PR's `README.md` in the GitHub UI ("Files changed" → view file) in both dark and light browser themes. Verify: hero renders with sunset gradient + sheen; tiles sit 2-up on desktop and stack on mobile-width windows; every click target works (hero → onlydole.dev, tiles → newest items, chips → destinations). Report anything off before merging.

---

## Post-merge checklist (manual, after Taylor merges)

1. Trigger **Actions → Build profile → Run workflow** once and confirm the bot commit lands and the profile page renders.
2. Edit `data/reading.yaml` to the actual current book (seeded with the mockup's *Thinking in Systems*).
3. Optionally delete the visual-companion artifacts: `rm -rf .superpowers/` (already gitignored).
