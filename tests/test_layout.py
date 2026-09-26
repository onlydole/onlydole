from itertools import pairwise

from generator import build
from generator.layout import (
    TILE_HEIGHT,
    TILE_STAGGER,
    hero_layout,
    hero_mobile_layout,
    tile_layout,
)


def _lines(title: str) -> list[dict]:
    return [{"primary": title, "secondary": "2026-01-02"}]


def test_tile_text_block_is_vertically_centered():
    short = tile_layout(_lines("Short"), 0)
    long = tile_layout(_lines("A title long enough to wrap " * 4), 0)
    assert len(short["primary"]) == 1
    assert len(long["primary"]) == 2
    for layout in (short, long):
        top = layout["header_y"] - 11
        bottom = layout["secondary_y"] + 4
        assert abs(top - (TILE_HEIGHT - bottom)) <= 1


def test_cards_take_turns():
    sweeps = [tile_layout(_lines("x"), i)["motion"]["sweep"] for i in range(5)]
    gaps = {round(b - a, 2) for a, b in pairwise(sweeps)}
    assert gaps == {TILE_STAGGER}
    # One full sweep of all five cards fits inside a single cycle.
    layout = tile_layout(_lines("x"), 4)
    assert layout["motion"]["cycle"] >= TILE_STAGGER * 5


def test_hero_graph_follows_the_career_in_order():
    graph = hero_layout(build.HERO)
    stops = graph["stops"]
    assert [s["name"] for s in stops] == [name for name, _ in build.HERO["career"]]
    assert [s["x"] for s in stops] == sorted(s["x"] for s in stops)
    assert [s["at"] for s in stops] == sorted(s["at"] for s in stops)
    assert [s["head"] for s in stops] == [False, False, False, True]
    # The upstream lane lands on HEAD exactly when HEAD lands.
    upstream = graph["upstream"]
    assert round(upstream["at"] + upstream["dur"], 2) == stops[-1]["at"]


def test_hero_tags_fit_between_fork_and_merge_without_touching():
    graph = hero_layout(build.HERO)
    pills = graph["pills"]
    assert [p["label"] for p in pills] == list(build.HERO["upstream"])
    for left, right in pairwise(pills):
        assert left["x"] + left["width"] + 8 <= right["x"]
        assert left["at"] < right["at"]
    assert pills[0]["x"] > graph["stops"][0]["x"]
    assert pills[-1]["x"] + pills[-1]["width"] < graph["stops"][-1]["x"]


def test_hero_graph_stays_left_of_the_illustration():
    graph = hero_layout(build.HERO)
    rightmost = graph["head_pill"]["x"] + graph["head_pill"]["width"]
    assert rightmost < graph["art"]["x"] + 200  # the art's left third is empty


def test_sun_glow_sits_on_the_sun():
    for graph in (hero_layout(build.HERO), hero_mobile_layout(build.HERO)):
        art, sun = graph["art"], graph["sun"]
        assert art["x"] < sun["cx"] < art["x"] + art["width"]
        assert art["y"] < sun["cy"] < art["y"] + art["height"] / 3


def test_mobile_legend_names_every_upstream_commit():
    graph = hero_mobile_layout(build.HERO)
    assert len(graph["commits"]) == len(build.HERO["upstream"])
    assert [item["label"] for item in graph["legend"]] == [
        label.upper() for label in build.HERO["upstream"]
    ]
    assert graph["legend"][-1]["y"] < graph["tagline_y"][0] - 20
