"""Render SVG assets from Jinja2 templates."""

from pathlib import Path
import unicodedata

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


def wrap_text(text: str, width: int, size: int, limit: int = 2) -> list[str]:
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
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        keep_trailing_newline=True,
    )
    if template_name == "tile.svg.j2":
        context = dict(context)
        available = context["width"] - context["text_x"] - 64
        y = 126
        rows = []
        for line in context["lines"]:
            primary = wrap_text(line["primary"], available, 30)
            secondary = wrap_text(line["secondary"], available, 20, limit=1)[0]
            rows.append({"primary": primary, "secondary": secondary, "y": y})
            y += len(primary) * 38 + 54
        context["rows"] = rows
        context["height"] = max(context["height"], y + 12)
    return env.get_template(template_name).render(**context)
