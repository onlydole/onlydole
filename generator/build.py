"""Build the bento dashboard: fetch sources, render SVGs, rewrite README."""

from __future__ import annotations

import base64
import datetime
import functools
import html
import json
import os
import sys
from pathlib import Path

import httpx

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import sources
from generator.layout import hero_layout, hero_mobile_layout, tile_layout
from generator.readme import replace_region
from generator.render import FONT_SANS, FONT_SERIF, HERO_THEMES, THEMES, render_svg

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "assets"
CACHE = ASSETS / "data-cache.json"
README = REPO_ROOT / "README.md"
EDITORIAL_ART = REPO_ROOT / "generator" / "art" / "la-field-notes.webp"

SITE = "https://onlydole.dev"
SUBSTACK_HOME = "https://onlydole.substack.com"
PODCAST_HOME = "https://attentiondeficitpod.substack.com"
CHIPS = [
    ("substack", "Substack", SUBSTACK_HOME),
    ("linkedin", "LinkedIn", "https://www.linkedin.com/in/onlydole"),
    ("bluesky", "Bluesky", "https://bsky.app/profile/onlydole.dev"),
    ("website", "Website", SITE),
]
# Everything the hero says, in one place. The templates and the alt text
# both read from here, so the picture and its description can't drift.
HERO = {
    "name": "Taylor Dolezal",
    "role": "Head of Open Source at Dosu",
    "place": "Los Angeles",
    "kicker": "OPEN SOURCE  /  LOS ANGELES",
    # Line breaks are art direction, so each layout sets its own.
    "mission": {
        "desktop": (
            "Building open source communities, making useful things,",
            "and sharing what I learn.",
        ),
        "mobile": (
            "Building open source communities,",
            "making useful things, and sharing",
            "what I learn.",
        ),
    },
    "tagline": "The project is code. The work is people.",
    # Day jobs, oldest first. The last stop is HEAD.
    "career": (
        ("Disney Studios", "Lead SRE"),
        ("HashiCorp", "Developer Advocate"),
        ("CNCF", "Head of Ecosystem"),
        ("Dosu", "Head of Open Source"),
    ),
    # Community work that ran alongside the day jobs and merges into HEAD.
    "upstream": ("Kubernetes 1.19 lead", "SIG Docs tech lead", "KubeCon keynoter"),
}
EMPTY_LINES = [{"primary": "—", "secondary": ""}]

# Per-card accents as (dark, light).
ACCENTS = {
    "writing": ("#f29a78", "#a74735"),
    "podcast": ("#b4a1d8", "#66508f"),
    "shipped": ("#93b9a7", "#3f725d"),
    "stage": ("#d7b168", "#8a6220"),
    "reading": ("#8fafd0", "#466f98"),
}
SOURCE_KEYS = ("writing", "podcast", "shipped", "stage", "reading")
# Feeds that can come through a caching relay, whose snapshot may lag.
RELAYED = ("writing", "podcast")
COVER_MAX_BYTES = 80_000
COVER_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
# Days a source may serve its cache before the card is labeled and the
# scheduled run fails. Substack blocks hosted runners, so both Substack
# cards depend on a free relay that misses a refresh now and then. A
# missed six-hour refresh is normal; no success today or yesterday isn't.
STALE_AFTER_DAYS = 1


def is_stale(status: dict, today: str) -> bool:
    """True when a source has gone past its refresh budget."""
    if status.get("state") == "fresh":
        return False
    try:
        last = datetime.date.fromisoformat(status.get("last_success") or "")
        age = datetime.date.fromisoformat(today) - last
    except (TypeError, ValueError):
        return True
    return age.days > STALE_AFTER_DAYS


def hero_alt() -> str:
    career = ", ".join(f"{name} ({role})" for name, role in HERO["career"])
    return (
        f"{HERO['name']}, {HERO['role']}, in {HERO['place']}. "
        f"{' '.join(HERO['mission']['desktop'])} "
        f"Career so far: {career}. "
        f"Alongside: {', '.join(HERO['upstream'])}. {HERO['tagline']}"
    )


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
            if mime.strip().lower() not in COVER_TYPES:
                print(f"warning: cover is not a raster image ({mime})", file=sys.stderr)
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
        "mime": mime.strip().lower(),
    }


def _fetch_reading(cached: object) -> dict:
    """Fetch Goodreads books, reusing the cached cover when its URL matches."""
    books = sources.fetch_goodreads()
    image_url = (books[0].get("image_url") or "") if books else ""
    cached_cover = (cached.get("cover") if isinstance(cached, dict) else None) or {}
    cover = None
    if image_url and cached_cover.get("url") == image_url and cached_cover.get("b64"):
        cover = cached_cover
    elif image_url:
        cover = _download_cover(image_url)
    return {"books": books, "cover": cover}


def _fetch_activity() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise sources.SourceError("GITHUB_TOKEN is not set")
    return sources.fetch_activity(token)


def _newest_stamp(items: object) -> str:
    """Publication stamp of a feed's newest post, or '' if unknown."""
    try:
        first = items[0]
        return str(first.get("published_at") or first.get("date") or "")
    except (IndexError, KeyError, TypeError, AttributeError):
        return ""


def _write_summary(statuses: dict) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    rows = [
        "## Profile sources\n",
        "| Source | Status | Last success | Transport |",
        "| --- | --- | --- | --- |",
    ]
    for key, status in statuses.items():
        transport = (
            status.get("via", "direct") if status["state"] == "fresh" else "local cache"
        )
        rows.append(
            f"| {key} | {status['state']} | {status['last_success'] or 'unknown'} "
            f"| {transport} |"
        )
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(rows) + "\n")


def gather(today: str) -> dict:
    """Fetch every source; fall back to last-good cache on failure."""
    cache = _load_cache()
    fetchers = {
        "writing": sources.fetch_substack,
        "podcast": sources.fetch_podcast,
        "shipped": _fetch_activity,
        "stage": sources.fetch_talks,
        "reading": lambda: _fetch_reading(cache.get("reading")),
    }
    previous = cache.get("source_status")
    previous = previous if isinstance(previous, dict) else {}
    data, statuses = {}, {}
    for key in SOURCE_KEYS:
        try:
            fresh = fetchers[key]()
            if key in RELAYED and _newest_stamp(fresh) < _newest_stamp(cache.get(key)):
                raise sources.SourceError(
                    "feed returned older posts than the last-good cache"
                )
        except sources.SourceError as exc:
            print(f"warning: {key}: {exc}; using last-good data", file=sys.stderr)
            data[key] = cache.get(key)
            last = previous.get(key)
            statuses[key] = {
                "state": "cached" if data[key] else "unavailable",
                "last_success": last.get("last_success")
                if isinstance(last, dict)
                else None,
            }
            if os.environ.get("GITHUB_ACTIONS"):
                print(
                    "::warning title=Profile source unavailable::"
                    f"{key} is {statuses[key]['state']}"
                )
            continue
        data[key] = cache[key] = fresh
        statuses[key] = {"state": "fresh", "last_success": today}
        if key in RELAYED and fresh and fresh[0].get("via"):
            statuses[key]["via"] = fresh[0]["via"]
    cache["source_status"] = statuses
    cache["updated"] = today
    data["_sources"] = statuses
    data["_today"] = today
    ASSETS.mkdir(exist_ok=True)
    CACHE.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_summary(statuses)
    return data


def _summary(lines: list[dict]) -> str:
    if lines is EMPTY_LINES:
        return "nothing to show right now"
    parts = []
    for line in lines:
        if line["primary"] and line["secondary"]:
            parts.append(f"{line['primary']} ({line['secondary']})")
        elif line["primary"] or line["secondary"]:
            parts.append(line["primary"] or line["secondary"])
    return "; ".join(parts) or "no items"


def _dated_lines(posts: list[dict] | None) -> list[dict]:
    if not posts:
        return EMPTY_LINES
    return [
        {"primary": p["title"], "secondary": p["date"], "url": p["url"]} for p in posts
    ]


def tile_contexts(data: dict) -> list[dict]:
    writing = data.get("writing")
    podcast = data.get("podcast")

    shipped = data.get("shipped")
    shipped_lines = (
        [
            {
                "primary": i["title"],
                "secondary": f"{i['detail']} · {i['date']}",
                "display_secondary": f"{i['detail'].split(' · ')[-1]} · {i['date']}",
                "url": i["url"],
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
                "primary": t["title"],
                "secondary": f"{t['venue']} · {t['date']}",
                "url": t["url"],
            }
            for t in stage
        ]
        if stage
        else EMPTY_LINES
    )

    reading = data.get("reading")
    books = (reading.get("books") if isinstance(reading, dict) else None) or []
    reading_lines = [
        {
            "primary": b["title"],
            "secondary": " ".join(b["author"].split()),
            "url": b["url"],
        }
        for b in books
    ] or EMPTY_LINES

    tiles = [
        {
            "key": "writing",
            "header": "LATEST WRITING",
            "action": "READ",
            "lines": _dated_lines(writing),
            "url": writing[0]["url"] if writing else SUBSTACK_HOME,
            "alt_prefix": "Latest writing",
        },
        {
            "key": "podcast",
            "header": "ATTENTION DEFICIT",
            "action": "LISTEN",
            "header_note": "with Alexa Griffith",
            "lines": _dated_lines(podcast),
            "url": podcast[0]["url"] if podcast else PODCAST_HOME,
            "alt_prefix": "Attention Deficit, with Alexa Griffith",
        },
        {
            "key": "shipped",
            "header": "RECENTLY SHIPPED",
            "action": "VIEW",
            "lines": shipped_lines,
            "url": shipped[0]["url"]
            if shipped
            else f"https://github.com/{sources.GITHUB_LOGIN}",
            "alt_prefix": "Recently shipped",
        },
        {
            "key": "stage",
            "header": "ON STAGE",
            "action": "WATCH",
            "lines": stage_lines,
            "url": stage[0]["url"] if stage else SITE,
            "alt_prefix": "On stage",
        },
        {
            "key": "reading",
            "header": "ON MY BOOKSHELF",
            "action": "EXPLORE",
            "header_note": "via Goodreads",
            "cover": reading.get("cover") if books else None,
            "lines": reading_lines,
            "url": books[0]["url"] if books else sources.GOODREADS_SHELF,
            "alt_prefix": "Currently-reading shelf on Goodreads",
        },
    ]
    for tile in tiles:
        tile["alt"] = f"{tile.pop('alt_prefix')}: {_summary(tile['lines'])}"
        status = data.get("_sources", {}).get(tile["key"], {})
        if status and is_stale(status, data["_today"]):
            tile["header_note"] = (
                f"{status['state']} · last fetched {status['last_success'] or 'unknown'}"
            )
    return tiles


ART_TYPES = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg"}


@functools.cache
def _art() -> tuple[str, str]:
    mime = ART_TYPES[EDITORIAL_ART.suffix.lower()]
    return mime, base64.b64encode(EDITORIAL_ART.read_bytes()).decode()


def hero_context(theme: str, mobile: bool = False) -> dict:
    art_mime, art_b64 = _art()
    layout = hero_mobile_layout(HERO) if mobile else hero_layout(HERO)
    first, _, rest = HERO["tagline"].partition(". ")
    return {
        "sans": FONT_SANS,
        "serif": FONT_SERIF,
        "aria": hero_alt(),
        "art_mime": art_mime,
        "art_b64": art_b64,
        "t": HERO_THEMES[theme],
        "g": layout,
        "name": HERO["name"],
        "role": HERO["role"],
        "kicker": HERO["kicker"],
        "mission": HERO["mission"]["mobile" if mobile else "desktop"],
        "tagline": HERO["tagline"],
        "tagline_lines": (f"{first}.", rest) if rest else (HERO["tagline"], ""),
    }


def write_assets(tiles: list[dict]) -> None:
    """Write every SVG and delete SVGs this build no longer produces."""
    ASSETS.mkdir(exist_ok=True)
    written: dict[str, str] = {}
    for theme in THEMES:
        written[f"hero-{theme}.svg"] = render_svg("hero.svg.j2", hero_context(theme))
        written[f"hero-mobile-{theme}.svg"] = render_svg(
            "hero-mobile.svg.j2", hero_context(theme, mobile=True)
        )
    for index, tile in enumerate(tiles):
        layout = tile_layout(tile["lines"], index)
        for theme_name, theme in THEMES.items():
            accent = ACCENTS[tile["key"]][0 if theme_name == "dark" else 1]
            written[f"{tile['key']}-{theme_name}.svg"] = render_svg(
                "tile.svg.j2",
                {
                    "sans": FONT_SANS,
                    "serif": FONT_SERIF,
                    "theme": {**theme, "accent": accent},
                    "layout": layout,
                    "header": tile["header"],
                    "action": tile["action"],
                    "key": tile["key"],
                    "aria": tile["alt"],
                    "cover": tile.get("cover"),
                    "header_note": tile.get("header_note", ""),
                },
            )
    for key, label, _url in CHIPS:
        for theme_name, theme in THEMES.items():
            written[f"chip-{key}-{theme_name}.svg"] = render_svg(
                "chip.svg.j2",
                {"font": FONT_SANS, "theme": theme, "label": label, "key": key},
            )
    for name, svg in written.items():
        (ASSETS / name).write_text(svg, encoding="utf-8")
    for orphan in ASSETS.glob("*.svg"):
        if orphan.name not in written:
            orphan.unlink()


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _picture(key: str, alt: str, width: str) -> str:
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" '
        f'srcset="assets/{key}-dark.svg">'
        f'<img src="assets/{key}-light.svg" width="{width}" alt="{_esc(alt)}">'
        f"</picture>"
    )


def _hero_picture() -> str:
    # The first matching source wins, so the phone layouts come first.
    phone = "(max-width: 600px)"
    dark = "(prefers-color-scheme: dark)"
    return (
        f'<a href="{SITE}"><picture>'
        f'<source media="{phone} and {dark}" srcset="assets/hero-mobile-dark.svg">'
        f'<source media="{phone}" srcset="assets/hero-mobile-light.svg">'
        f'<source media="{dark}" srcset="assets/hero-dark.svg">'
        f'<img src="assets/hero-light.svg" width="100%" alt="{_esc(hero_alt())}">'
        f"</picture></a>"
    )


def bento_html(tiles: list[dict]) -> str:
    rows = [_hero_picture()]
    link_sections = []
    for tile in tiles:
        picture = _picture(tile["key"], tile["alt"], "100%")
        rows.append(
            f'<p align="center">\n  <a href="{_esc(tile["url"])}">{picture}</a>\n</p>'
        )
        links = [
            f'<li><a href="{_esc(line["url"])}">{_esc(line["primary"])}</a> · {_esc(line["secondary"])}</li>'
            for line in tile["lines"]
            if line.get("url")
        ]
        if links:
            link_sections.append(
                f"<li><strong>{_esc(tile['header'].title())}</strong>\n<ul>\n"
                + "\n".join(links)
                + "\n</ul>\n</li>"
            )
    if link_sections:
        rows.append(
            "<details>\n<summary>Browse all field notes and individual links</summary>\n<ul>\n"
            + "\n".join(link_sections)
            + "\n</ul>\n</details>\n"
        )
    chips = [
        f'<a href="{_esc(url)}">{_picture("chip-" + key, label, "150")}</a>'
        for key, label, url in CHIPS
    ]
    rows.append('<p align="center">\n  ' + "\n  ".join(chips) + "\n</p>")
    return "\n".join(rows)


def main() -> int:
    today = (
        os.environ.get("BUILD_DATE")
        or datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    )
    data = gather(today)
    tiles = tile_contexts(data)
    write_assets(tiles)
    content = README.read_text(encoding="utf-8")
    content = replace_region(content, "bento", "\n" + bento_html(tiles) + "\n")
    failed = [
        key for key, status in data["_sources"].items() if is_stale(status, today)
    ]
    stamp = f"Last refreshed: {today}"
    if failed:
        stamp = f"Built: {today} · cached or unavailable: {', '.join(failed)}"
    content = replace_region(content, "stamp", stamp)
    README.write_text(content, encoding="utf-8")
    print("profile rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
