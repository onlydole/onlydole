"""Fixture contexts shared by the golden test and the regenerator."""

from generator import build
from generator.layout import tile_layout
from generator.render import DARK, FONT_SANS, FONT_SERIF, LIGHT

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _hero(theme: str, mobile: bool = False) -> dict:
    # The real hero data and layout, with a one-pixel stand-in for the art.
    context = build.hero_context(theme, mobile=mobile)
    return {**context, "art_mime": "image/png", "art_b64": TINY_PNG_B64}


def _tile(theme: dict, key: str, lines: list[dict], index: int, **extra) -> dict:
    return {
        "sans": FONT_SANS,
        "serif": FONT_SERIF,
        "theme": theme,
        "layout": tile_layout(lines, index),
        "key": key,
        "cover": None,
        "header_note": "",
        **extra,
    }


CASES = {
    "hero-light.svg": ("hero.svg.j2", _hero("light")),
    "hero-dark.svg": ("hero.svg.j2", _hero("dark")),
    "hero-mobile-dark.svg": ("hero-mobile.svg.j2", _hero("dark", mobile=True)),
    "tile-writing-dark.svg": (
        "tile.svg.j2",
        _tile(
            DARK,
            "writing",
            [
                {"primary": "Fixture post", "secondary": "2026-01-02"},
                {"primary": "Second post with <angle> & amp", "secondary": "2026"},
            ],
            0,
            header="LATEST WRITING",
            action="READ",
            aria="Latest writing: Fixture post (2026-01-02)",
        ),
    ),
    "tile-shipped-light.svg": (
        "tile.svg.j2",
        _tile(
            LIGHT,
            "shipped",
            [
                {
                    "primary": "A merged pull request whose title is long enough "
                    "to wrap onto a second line of the card and then some",
                    "secondary": "merged · onlydole/repo · 2026-01-02",
                    "display_secondary": "onlydole/repo · 2026-01-02",
                }
            ],
            2,
            header="RECENTLY SHIPPED",
            action="VIEW",
            aria="Recently shipped: fixture",
        ),
    ),
    "tile-reading-cover-dark.svg": (
        "tile.svg.j2",
        _tile(
            DARK,
            "reading",
            [{"primary": "Fixture book", "secondary": "Fixture author"}],
            4,
            cover={"mime": "image/png", "b64": TINY_PNG_B64},
            header_note="via Goodreads",
            header="ON MY BOOKSHELF",
            action="EXPLORE",
            aria="Currently-reading shelf on Goodreads: Fixture book (Fixture author)",
        ),
    ),
    "chip-bluesky-dark.svg": (
        "chip.svg.j2",
        {"font": FONT_SANS, "theme": DARK, "label": "Bluesky", "key": "bluesky"},
    ),
}
