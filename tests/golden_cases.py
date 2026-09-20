"""Fixture contexts shared by the golden test and the regenerator."""

from generator.render import DARK, FONT_SANS, FONT_SERIF, LIGHT

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

CASES = {
    "hero.svg": (
        "hero.svg.j2",
        {
            "sans": FONT_SANS,
            "serif": FONT_SERIF,
            "aria": "Taylor Dolezal, Head of Open Source at Dosu in Los Angeles.",
            "name": "Taylor Dolezal",
            "role": "Head of Open Source at Dosu",
            "mission": "I help open source communities thrive.",
            "illustration_b64": TINY_PNG_B64,
            "credentials": [
                "Kubernetes 1.19 Release Lead",
                "CNCF Head of Ecosystem",
                "KubeCon keynoter",
                "Technical author",
            ],
        },
    ),
    "tile-writing-dark.svg": (
        "tile.svg.j2",
        {
            "sans": FONT_SANS,
            "serif": FONT_SERIF,
            "theme": DARK,
            "width": 1200,
            "height": 176,
            "text_x": 174,
            "cover": None,
            "header_note": "",
            "header": "✍️ LATEST WRITING",
            "action": "READ",
            "more_count": 1,
            "key": "writing",
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
            "sans": FONT_SANS,
            "serif": FONT_SERIF,
            "theme": LIGHT,
            "width": 1200,
            "height": 176,
            "text_x": 174,
            "cover": None,
            "header_note": "",
            "header": "✍️ LATEST WRITING",
            "action": "READ",
            "more_count": 0,
            "key": "writing",
            "aria": "Latest writing: Fixture post (2026-01-02)",
            "lines": [{"primary": "Fixture post", "secondary": "2026-01-02"}],
        },
    ),
    "tile-reading-cover-dark.svg": (
        "tile.svg.j2",
        {
            "sans": FONT_SANS,
            "serif": FONT_SERIF,
            "theme": DARK,
            "width": 1200,
            "height": 176,
            "text_x": 174,
            "cover": {"mime": "image/png", "b64": TINY_PNG_B64},
            "header_note": "via Goodreads",
            "header": "📚 READING NOW",
            "action": "EXPLORE",
            "more_count": 0,
            "key": "reading",
            "aria": "Reading now: Fixture book (Fixture author)",
            "lines": [{"primary": "Fixture book", "secondary": "Fixture author"}],
        },
    ),
    "tile-writing-mobile-dark.svg": (
        "tile.svg.j2",
        {
            "sans": FONT_SANS,
            "serif": FONT_SERIF,
            "theme": DARK,
            "width": 600,
            "height": 96,
            "text_x": 94,
            "cover": None,
            "header_note": "",
            "header": "LATEST WRITING",
            "action": "READ",
            "more_count": 0,
            "key": "writing",
            "aria": "Latest writing: A long fixture post title (2026-01-02)",
            "lines": [
                {
                    "primary": "A long fixture post title that must fit one line",
                    "secondary": "2026-01-02",
                }
            ],
        },
    ),
    "tile-writing-mobile-light.svg": (
        "tile.svg.j2",
        {
            "sans": FONT_SANS,
            "serif": FONT_SERIF,
            "theme": LIGHT,
            "width": 600,
            "height": 96,
            "text_x": 94,
            "cover": None,
            "header_note": "",
            "header": "LATEST WRITING",
            "action": "READ",
            "more_count": 0,
            "key": "writing",
            "aria": "Latest writing: Fixture post (2026-01-02)",
            "lines": [{"primary": "Fixture post", "secondary": "2026-01-02"}],
        },
    ),
    "tile-reading-cover-mobile-dark.svg": (
        "tile.svg.j2",
        {
            "sans": FONT_SANS,
            "serif": FONT_SERIF,
            "theme": DARK,
            "width": 600,
            "height": 96,
            "text_x": 94,
            "cover": {"mime": "image/png", "b64": TINY_PNG_B64},
            "header_note": "via Goodreads",
            "header": "ON MY BOOKSHELF",
            "action": "EXPLORE",
            "more_count": 0,
            "key": "reading",
            "aria": "Reading now: Fixture book (Fixture author)",
            "lines": [{"primary": "Fixture book", "secondary": "Fixture author"}],
        },
    ),
    "chip-substack-dark.svg": (
        "chip.svg.j2",
        {"font": FONT_SANS, "theme": DARK, "label": "Substack"},
    ),
}
