"""Regenerate golden SVGs. Run from repo root:
uv run --project generator python tests/update_goldens.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.render import render_svg          # noqa: E402
from tests.golden_cases import CASES             # noqa: E402

GOLDENS = Path(__file__).parent / "goldens"

if __name__ == "__main__":
    GOLDENS.mkdir(exist_ok=True)
    for name, (template, context) in CASES.items():
        (GOLDENS / name).write_text(render_svg(template, context), encoding="utf-8")
        print(f"wrote {name}")
