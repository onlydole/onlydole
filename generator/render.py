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
