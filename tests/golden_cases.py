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
