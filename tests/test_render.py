from pathlib import Path

from generator.render import fit, render_svg
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
    svg = render_svg("tile.svg.j2", context)
    assert "&lt;angle&gt; &amp; amp" in svg
    assert "<angle>" not in svg
