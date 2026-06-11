"""Build the bento dashboard: fetch sources, render SVGs, rewrite README."""

from __future__ import annotations

import base64
import datetime
import html
import httpx
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
    "role": "Head of Open Source @ Dosu · Open Source Strategy & Ecosystems · Los Angeles",
    "cred": "KubeCon keynoter · ex-Disney Studios SRE · ex-HashiCorp",
}
HERO_ALT = (
    "Taylor Dolezal — Head of Open Source at Dosu · "
    "Open Source Strategy & Ecosystems · Los Angeles"
)
EMPTY_LINES = [{"primary": "—", "secondary": ""}]

TILE_WIDTH = 1200
TEXT_X = 36
TEXT_X_WITH_COVER = 156
COVER_MAX_BYTES = 80_000


def _load_cache() -> dict:
    if not CACHE.exists():
        return {}
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: cache unreadable ({exc}); starting fresh", file=sys.stderr)
        return {}
    return cache if isinstance(cache, dict) else {}


def _download_cover(url: str) -> dict | None:
    try:
        with httpx.stream(
            "GET",
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": sources.USER_AGENT},
        ) as resp:
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            if not mime.startswith("image/"):
                print(f"warning: cover is not an image ({mime})", file=sys.stderr)
                return None
            chunks = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > COVER_MAX_BYTES:
                    print("warning: cover exceeds size cap, skipping", file=sys.stderr)
                    return None
                chunks.append(chunk)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        print(f"warning: cover download failed: {exc}", file=sys.stderr)
        return None
    return {
        "url": url,
        "b64": base64.b64encode(b"".join(chunks)).decode(),
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


def gather(today: str) -> dict:
    """Fetch every source; fall back to last-good cache on failure."""
    cache = _load_cache()
    fetchers = {
        "writing": lambda: sources.fetch_substack(),
        "shipped": lambda: sources.fetch_activity(os.environ["GITHUB_TOKEN"]),
        "stage": lambda: sources.fetch_talks(),
    }
    data = {}
    for key, fetch in fetchers.items():
        try:
            data[key] = fetch()
            cache[key] = data[key]
        except (sources.SourceError, KeyError) as exc:
            print(f"warning: {key}: {exc}; using last-good data", file=sys.stderr)
            data[key] = cache.get(key)
    data["reading"] = _resolve_reading(cache)
    cache["updated"] = today
    ASSETS.mkdir(exist_ok=True)
    CACHE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return data


def _summary(lines: list[dict]) -> str:
    parts = []
    for line in lines:
        if line["primary"] and line["secondary"]:
            parts.append(f"{line['primary']} ({line['secondary']})")
        elif line["primary"] or line["secondary"]:
            parts.append(line["primary"] or line["secondary"])
    return "; ".join(parts) or "no items"


def tile_contexts(data: dict) -> list[dict]:
    writing = data.get("writing")
    writing_lines = (
        [{"primary": fit(p["title"], 92), "secondary": p["date"]} for p in writing]
        if writing
        else EMPTY_LINES
    )

    shipped = data.get("shipped")
    shipped_lines = (
        [
            {
                "primary": fit(i["title"], 92),
                "secondary": fit(f"{i['detail']} · {i['date']}", 110),
            }
            for i in shipped
        ]
        if shipped
        else EMPTY_LINES
    )

    stage = data.get("stage")
    stage_lines = (
        [
            {
                "primary": fit(t["title"], 92),
                "secondary": fit(f"{t['venue']} · {t['date']}", 110),
            }
            for t in stage
        ]
        if stage
        else EMPTY_LINES
    )

    reading = data.get("reading")
    books = (reading or {}).get("books") or []
    if books:
        reading_lines = [
            {"primary": fit(b["title"], 92), "secondary": fit(b["author"], 110)}
            for b in books
        ]
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
            "url": shipped[0]["url"]
            if shipped
            else f"https://github.com/{sources.GITHUB_LOGIN}",
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
            "header_note": "via Goodreads" if books else "",
            "cover": (reading or {}).get("cover") if books else None,
            "lines": reading_lines,
            "url": books[0]["url"] if books else "",
            "alt": "Reading now: " + _summary(reading_lines),
        },
    ]


def _tile_geometry(tile: dict) -> dict:
    height = 88 + 74 * len(tile["lines"]) + 26
    if tile.get("cover"):
        height = max(height, 250)
    return {
        "width": TILE_WIDTH,
        "height": height,
        "text_x": TEXT_X_WITH_COVER if tile.get("cover") else TEXT_X,
    }


def write_assets(tiles: list[dict]) -> None:
    ASSETS.mkdir(exist_ok=True)
    hero_ctx = {"font": FONT_STACK, "aria": HERO_ALT, **HERO}
    (ASSETS / "hero.svg").write_text(
        render_svg("hero.svg.j2", hero_ctx), encoding="utf-8"
    )
    themes = (("dark", DARK), ("light", LIGHT))
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
