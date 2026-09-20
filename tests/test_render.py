import xml.etree.ElementTree as ET
from pathlib import Path

from generator.render import fit, render_svg, text_width, wrap_text
from tests.golden_cases import CASES

GOLDENS = Path(__file__).parent / "goldens"


def test_fit_short_text_unchanged():
    assert fit("hello", 10) == "hello"


def test_fit_truncates_with_ellipsis():
    assert fit("a long title here", 8) == "a long…"


def test_fit_exact_length_unchanged():
    assert fit("12345678", 8) == "12345678"


def test_fit_collapses_internal_whitespace():
    assert fit("a\n  b\tc", 20) == "a b c"


def test_rendered_svgs_match_goldens():
    for name, (template, context) in CASES.items():
        golden = GOLDENS / name
        assert golden.exists(), f"missing golden {name}; run tests/update_goldens.py"
        assert render_svg(template, context) == golden.read_text(encoding="utf-8"), name


def test_svg_output_escapes_xml():
    _, context = CASES["tile-writing-dark.svg"]
    context = {
        **context,
        "lines": [{"primary": "Post with <angle> & amp", "secondary": "today"}],
    }
    svg = render_svg("tile.svg.j2", context)
    assert "&lt;angle&gt; &amp; amp" in svg
    assert "<angle>" not in svg


def test_mobile_tile_keeps_one_readable_ellipsized_title_line():
    _, desktop = CASES["tile-writing-dark.svg"]
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    for title in ["W" * 160, "本" * 160, "An unusually long post title " * 12]:
        context = {
            **desktop,
            "width": 600,
            "height": 96,
            "text_x": 94,
            "lines": [{"primary": title, "secondary": "2026-09-20"}],
        }
        root = ET.fromstring(render_svg("tile.svg.j2", context))
        text = root.findall("svg:text", namespace)

        assert len(text) == 3
        assert text[1].attrib["font-size"] == "29"
        assert text[1].text.endswith("…")
        assert text_width(text[1].text, 29) <= 486


def test_wide_and_unbroken_titles_fit_the_reading_column():
    for title in ["W" * 160, "本" * 160, "An unusually long book title " * 12]:
        lines = wrap_text(title, 980, 30)
        assert len(lines) <= 2
        assert all(text_width(line, 30) <= 980 for line in lines)
        assert lines[-1].endswith("…")
