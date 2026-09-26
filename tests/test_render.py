import re
from pathlib import Path

from generator.render import render_svg, text_width, wrap_text
from tests.golden_cases import CASES

GOLDENS = Path(__file__).parent / "goldens"


def test_rendered_svgs_match_goldens():
    for name, (template, context) in CASES.items():
        golden = GOLDENS / name
        assert golden.exists(), f"missing golden {name}; run tests/update_goldens.py"
        assert render_svg(template, context) == golden.read_text(encoding="utf-8"), name


def test_goldens_directory_has_no_orphans():
    assert {p.name for p in GOLDENS.glob("*.svg")} == set(CASES)


def test_svg_output_escapes_xml():
    _, context = CASES["tile-writing-dark.svg"]
    svg = render_svg(
        "tile.svg.j2",
        {**context, "aria": "Post with <angle> & amp"},
    )
    assert "&lt;angle&gt; &amp; amp" in svg
    assert "<angle>" not in svg


def test_wide_and_unbroken_titles_fit_the_reading_column():
    for title in ["W" * 160, "本" * 160, "An unusually long book title " * 12]:
        lines = wrap_text(title, 980, 30)
        assert len(lines) <= 2
        assert all(text_width(line, 30) <= 980 for line in lines)
        assert lines[-1].endswith("…")


def test_wrap_text_collapses_whitespace_and_keeps_short_text():
    assert wrap_text("a\n  b\tc", 500, 20) == ["a b c"]


def test_motion_always_ends_on_the_plain_drawing():
    """Animations only run from a hidden or partial state back to the SVG's
    own attributes, so a renderer without animation shows the finished card."""
    for name, (template, context) in CASES.items():
        svg = render_svg(template, context)
        if "@keyframes" not in svg:
            continue
        assert "prefers-reduced-motion: reduce" in svg, name
        assert "animation: none !important" in svg, name
        assert not re.search(r"\bforwards\b|\bboth\b", svg), name
        for keyframes in ("draw", "write"):
            match = re.search(rf"@keyframes {keyframes} \{{(.*?)\}} \}}", svg)
            if match:
                assert "stroke-dashoffset: 0" in match.group(1), (name, keyframes)


def test_text_never_starts_hidden():
    for name, (template, context) in CASES.items():
        svg = render_svg(template, context)
        for tag in re.findall(r"<text\b[^>]*>", svg):
            assert 'opacity="0"' not in tag, (name, tag)
