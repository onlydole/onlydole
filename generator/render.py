"""Render SVG assets from Jinja2 templates."""

import unicodedata
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_DIR = Path(__file__).parent / "templates"

# Undefined template variables fail the build instead of rendering blank.
ENV = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
    keep_trailing_newline=True,
    undefined=StrictUndefined,
)

DARK = {
    "bg": "#1d1816",
    "border": "#51433d",
    "accent": "#ff9d76",
    "text": "#f7efe5",
    "muted": "#b9a69c",
}
LIGHT = {
    "bg": "#faf3e9",
    "border": "#dfcfc0",
    "accent": "#c2414f",
    "text": "#2d2521",
    "muted": "#78665d",
}
THEMES = {"light": LIGHT, "dark": DARK}

# The hero is paper in daylight and the same city at night. The dark
# variant inverts the illustration's lightness and rotates its hue back,
# so ink lines turn pale while the sun keeps its color. There's no
# feTurbulence grain: animated SVGs repaint every frame, and noise is the
# most expensive filter to recompute.
HERO_THEMES = {
    "light": {
        "paper": ("#fffaf1", "#f8eee1", "#eedcca"),
        "fiber": "#654d42",
        "fiber_warm": "#b66c54",
        "kicker": "#944634",
        "name": "#281f1b",
        "role": "#3a2d28",
        "body": "#3f312b",
        "muted": "#6b574c",
        "ink": "#8c5a48",
        "accent": "#b6553e",
        "pill_text": "#fff8f0",
        "tagline": "#7b4639",
        "border": "#d5c0ae",
        "sun": "#ffb27a",
        "glow": (0.35, 0.8),
        "invert_art": False,
    },
    "dark": {
        "paper": ("#231c1a", "#1d1716", "#171211"),
        "fiber": "#f7efe5",
        "fiber_warm": "#ff9d76",
        "kicker": "#f0a07f",
        "name": "#f7efe5",
        "role": "#eadccf",
        "body": "#d9c9bb",
        "muted": "#b3a194",
        "ink": "#c99a84",
        "accent": "#f0916c",
        "pill_text": "#231c1a",
        "tagline": "#f0b49a",
        "border": "#4a3d37",
        "sun": "#ff8a5c",
        "glow": (0.25, 0.55),
        "invert_art": True,
    },
}

FONT_SANS = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
)
FONT_SERIF = "Georgia, 'Times New Roman', serif"


def text_width(text: str, size: int) -> float:
    """Conservative advance estimate for the system sans-serif fallback stack."""

    def advance(char: str) -> float:
        if unicodedata.east_asian_width(char) in ("W", "F"):
            return 1.1
        if char in "MW@%&":
            return 1.0
        if char in "il.,'!:;| ":
            return 0.35
        return 0.75 if char.isupper() else 0.62

    return sum(advance(char) for char in text) * size


def wrap_text(text: str, width: float, size: int, limit: int = 2) -> list[str]:
    """Wrap at words, split long tokens, and ellipsize only the final line."""
    remaining = " ".join(text.split())
    lines = []
    while remaining and len(lines) < limit:
        if text_width(remaining, size) <= width:
            lines.append(remaining)
            break
        end = 1
        while (
            end < len(remaining)
            and text_width(remaining[: end + 1] + "…", size) <= width
        ):
            end += 1
        if len(lines) == limit - 1:
            lines.append(remaining[:end].rstrip() + "…")
            break
        boundary = remaining.rfind(" ", 0, end + 1)
        end = boundary if boundary > 0 else end
        lines.append(remaining[:end].rstrip())
        remaining = remaining[end:].lstrip()
    return lines or [""]


def render_svg(template_name: str, context: dict) -> str:
    return ENV.get_template(template_name).render(**context)
