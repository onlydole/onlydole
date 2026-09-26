"""Geometry and motion timing for the hero and the activity cards.

Templates only loop over what this module computes. Every animation starts
from a hidden or partial state and ends on the element's plain SVG state,
so a renderer without animation support, or a visitor who prefers reduced
motion, sees the finished drawing.
"""

from __future__ import annotations

import math
from itertools import pairwise

from generator.render import text_width, wrap_text

TILE_WIDTH = 1200
TILE_HEIGHT = 176
TILE_TEXT_X = 174
TILE_TITLE_SIZE = 29
TILE_TEXT_RIGHT = 990  # leaves room for the action label and arrow

# Cards take turns: one card moves at a time, top to bottom, then all of
# them rest. Three sweeps play after the page loads, then the page is still.
TILE_CYCLE = 12.0
TILE_STAGGER = 2.4
TILE_FIRST_SWEEP = 3.2
TILE_SWEEPS = 3


def _round(value: float) -> float:
    return round(value, 2)


def tile_layout(lines: list[dict], index: int) -> dict:
    """Wrap the featured item and center the text block vertically."""
    featured = lines[0]
    available = TILE_TEXT_RIGHT - TILE_TEXT_X
    primary = wrap_text(featured["primary"], available, TILE_TITLE_SIZE, limit=2)
    secondary = wrap_text(
        featured.get("display_secondary", featured["secondary"]),
        available,
        17,
        limit=1,
    )[0]
    # Header cap height (11) + header-to-title (41) + title steps (31)
    # + title-to-meta (40) + meta descender (4).
    block = 96 + 31 * (len(primary) - 1)
    header_y = round((TILE_HEIGHT - block) / 2 + 11)
    title_y = [header_y + 41 + 31 * i for i in range(len(primary))]
    return {
        "width": TILE_WIDTH,
        "height": TILE_HEIGHT,
        "text_x": TILE_TEXT_X,
        "header_y": header_y,
        "title_y": title_y,
        "primary": primary,
        "secondary": secondary,
        "secondary_y": title_y[-1] + 40,
        "motion": {
            "enter": _round(0.15 + 0.12 * index),
            "sweep": _round(TILE_FIRST_SWEEP + TILE_STAGGER * index),
            "cycle": TILE_CYCLE,
            "sweeps": TILE_SWEEPS,
        },
    }


def _cubic(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def _cubic_length(p0, p1, p2, p3, steps: int = 48) -> float:
    points = [_cubic(p0, p1, p2, p3, i / steps) for i in range(steps + 1)]
    return sum(math.dist(a, b) for a, b in pairwise(points))


def _pill(label: str, size: int, cx: float, cy: float) -> dict:
    width = text_width(label, size) * 0.92 + 22
    return {
        "label": label,
        "x": _round(cx - width / 2),
        "y": _round(cy - 11),
        "width": _round(width),
        "cx": _round(cx),
    }


def _career_track(
    career: tuple, points: list[tuple[float, float]], draw: float, pause: float
) -> tuple[list[dict], list[dict]]:
    """Stops and lane segments for the day jobs, timed stop to stop.

    The pen draws one segment at a time and each stop lands as the ink
    reaches it, so the career reads in order.
    """
    start = 0.35
    stops, segments = [], []
    for i, ((name, role), (x, y)) in enumerate(zip(career, points, strict=True)):
        arrive = 0.2 if i == 0 else start + (i - 1) * (draw + pause) + draw
        stops.append(
            {
                "x": x,
                "y": y,
                "name": name,
                "role": role,
                "at": _round(arrive),
                "head": i == len(career) - 1,
            }
        )
        if i:
            px, py = points[i - 1]
            segments.append(
                {
                    "d": f"M{px} {py} L{x} {y}",
                    "at": _round(start + (i - 1) * (draw + pause)),
                    "dur": draw,
                }
            )
    return stops, segments


def hero_layout(hero: dict) -> dict:
    """Desktop hero: a left-to-right commit graph of the career.

    `main` carries the day jobs. An `upstream` lane forks off after the
    first stop, carries the community work as tags, and merges into HEAD.
    """
    width, height = 1200, 480
    main_y, upstream_y, step = 330, 298, 230
    points = [(58 + step * i, main_y) for i in range(len(hero["career"]))]
    stops, segments = _career_track(hero["career"], points, draw=0.7, pause=0.15)
    head = stops[-1]

    fork_x, merge_x, bend = points[0][0] + 60, head["x"], 40
    fork_end = (fork_x + bend, upstream_y)
    merge_start = merge_x - bend
    curve = _cubic_length(
        (fork_x, main_y), (fork_x + 24, main_y), (fork_x + 16, upstream_y), fork_end
    )
    run = merge_start - fork_end[0]
    total = 2 * curve + run
    upstream_at = 0.62
    upstream_dur = head["at"] - upstream_at
    upstream_d = (
        f"M{fork_x} {main_y} C{fork_x + 24} {main_y} {fork_x + 16} {upstream_y} "
        f"{fork_end[0]} {upstream_y} H{merge_start} "
        f"C{merge_x - 16} {upstream_y} {merge_x - 24} {main_y} {merge_x} {main_y}"
    )

    # Tags sit in equal slots along the run and land as the ink passes.
    labels = hero["upstream"]
    pills = []
    for i, label in enumerate(labels):
        cx = fork_end[0] + run * (i + 0.5) / len(labels)
        pill = _pill(label, 13, cx, upstream_y)
        travelled = curve + (cx - fork_end[0])
        pill["at"] = _round(upstream_at + upstream_dur * travelled / total)
        pills.append(pill)
    head_pill = _pill("HEAD", 11, head["x"] + 42, main_y)
    head_pill["at"] = _round(head["at"] + 0.1)

    art = {"x": 688, "y": 3, "width": 500, "height": height - 6}
    tagline_y = height - 42
    return {
        "width": width,
        "height": height,
        "mission_y": [222, 251],
        "stops": stops,
        "segments": segments,
        "upstream": {"d": upstream_d, "at": upstream_at, "dur": _round(upstream_dur)},
        "pills": pills,
        "head_pill": head_pill,
        "pulse_at": _round(head["at"] + 0.3),
        "tagline": {
            "y": tagline_y,
            "at": _round(head["at"] + 0.35),
            # Serif italic runs about 80% of the sans estimate.
            "underline": _round(52 + text_width(hero["tagline"], 21) * 0.8),
        },
        "art": art,
        "sun": _sun(**art),
    }


def hero_mobile_layout(hero: dict) -> dict:
    """Phone hero: the same graph, stacked top to bottom, with a legend."""
    width, height = 600, 690
    main_x, upstream_x = 54, 30
    points = [(main_x, 306 + 54 * i) for i in range(len(hero["career"]))]
    stops, segments = _career_track(hero["career"], points, draw=0.5, pause=0.12)
    head = stops[-1]

    fork_y, bend = points[0][1] + 26, 24
    upstream_d = (
        f"M{main_x} {fork_y} C{main_x} {fork_y + 16} {upstream_x} {fork_y + 8} "
        f"{upstream_x} {fork_y + bend} V{head['y'] - bend} "
        f"C{upstream_x} {head['y'] - 8} {main_x} {head['y'] - 16} {main_x} {head['y']}"
    )
    upstream_at = 0.55
    run_top, run_bottom = fork_y + bend, head["y"] - bend
    labels = hero["upstream"]
    commits = [
        {
            "x": upstream_x,
            "y": _round(run_top + (run_bottom - run_top) * (i + 0.5) / len(labels)),
            "at": _round(
                upstream_at + (head["at"] - upstream_at) * (i + 1) / (len(labels) + 1)
            ),
        }
        for i in range(len(labels))
    ]
    # There's no room for tags beside a vertical lane, so a legend below
    # names the upstream commits, one per line.
    legend_top = head["y"] + 64
    legend = [
        {"label": label.upper(), "y": legend_top + 24 * i, "at": commits[i]["at"]}
        for i, label in enumerate(labels)
    ]

    art = {"x": 300, "y": height - 446, "width": 292, "height": 440}
    return {
        "width": width,
        "height": height,
        "mission_y": [196, 226, 256],
        "stops": stops,
        "segments": segments,
        "upstream": {
            "d": upstream_d,
            "at": upstream_at,
            "dur": _round(head["at"] - upstream_at),
        },
        "commits": commits,
        "legend": legend,
        "pulse_at": _round(head["at"] + 0.3),
        "tagline_y": [height - 54, height - 28],
        "art": art,
        "sun": _sun(**art),
    }


# The sun in generator/art/la-field-notes.webp, in the image's own pixels.
ART_SIZE = (430, 645)
ART_SUN = (337, 86, 63)


def _sun(*, x: float, y: float, width: float, height: float) -> dict:
    """Place the sun's glow for an image drawn with xMaxYMid meet."""
    scale = min(width / ART_SIZE[0], height / ART_SIZE[1])
    left = x + width - ART_SIZE[0] * scale
    top = y + (height - ART_SIZE[1] * scale) / 2
    return {
        "cx": _round(left + ART_SUN[0] * scale),
        "cy": _round(top + ART_SUN[1] * scale),
        "r": _round(ART_SUN[2] * scale),
    }
