import re
import xml.etree.ElementTree as ET
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


def test_motion_is_opt_in_and_ends_on_the_plain_drawing():
    """Animation only runs for visitors with no reduced-motion preference,
    and only from a hidden or partial state back to the SVG's own
    attributes, so a renderer without animation shows the finished card."""
    marker = "@media (prefers-reduced-motion: no-preference) {"
    for name, (template, context) in CASES.items():
        svg = render_svg(template, context)
        if "@keyframes" not in svg:
            continue
        css = svg[svg.index("<style>") : svg.index("</style>")]
        before, _, motion = css.partition(marker)
        assert motion, name
        assert "animation" not in before, name
        assert "!important" not in svg, name
        assert not re.search(r'style="[^"]*animation', svg), name
        assert not re.search(r"\bforwards\b|\bboth\b", svg), name
        for keyframes in ("draw", "write"):
            match = re.search(rf"@keyframes {keyframes} \{{(.*?)\}} \}}", svg)
            if match:
                assert "stroke-dashoffset: 0" in match.group(1), (name, keyframes)


# Motion classes whose keyframes start at zero opacity or zero scale.
HIDING_CLASSES = {"rise", "pop", "land"}
SVG = "{http://www.w3.org/2000/svg}"


def _texts(node, hidden=False, graph=False):
    """Yield (content, starts_hidden, in_graph) for every <text>, taking
    the motion and opacity of all its ancestors into account."""
    classes = set((node.get("class") or "").split())
    hidden = hidden or bool(classes & HIDING_CLASSES) or node.get("opacity") == "0"
    graph = graph or node.get("aria-hidden") == "true"
    if node.tag == f"{SVG}text":
        yield "".join(node.itertext()), hidden, graph
    for child in node:
        yield from _texts(child, hidden, graph)


def _copy(template: str, context: dict) -> list[str]:
    """The lines a visitor must be able to read from the first frame."""
    if template.startswith("hero"):
        tagline = context["tagline"].split(". ")
        return [context["name"], context["role"], *context["mission"], *tagline]
    if template == "tile.svg.j2":
        layout = context["layout"]
        return [context["header"], *layout["primary"], layout["secondary"]]
    return [context["label"]]


def test_copy_never_starts_hidden():
    """Only the career graph's labels enter with their stops, and the alt
    text carries every one of them. All other copy is visible from the
    first frame, whatever its ancestors animate."""
    for name, (template, context) in CASES.items():
        texts = list(_texts(ET.fromstring(render_svg(template, context))))
        aria = context.get("aria", "").lower()
        for content, hidden, graph in texts:
            if hidden:
                assert graph, (name, content)
                assert content.replace("HEAD", "").strip().lower() in aria, (
                    name,
                    content,
                )
        shown = [content for content, hidden, _ in texts if not hidden]
        for line in _copy(template, context):
            assert any(line.strip(".") in content for content in shown), (name, line)
