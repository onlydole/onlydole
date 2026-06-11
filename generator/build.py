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
                    "lines": tile["lines"],
                    "header": tile["header"],
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
