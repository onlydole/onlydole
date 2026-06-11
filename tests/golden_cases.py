"""Fixture contexts shared by the golden test and the regenerator."""

from generator.render import DARK, FONT_STACK, LIGHT

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
