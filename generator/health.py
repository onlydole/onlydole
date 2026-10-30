"""Report sources past their refresh budget for the tracking issue.

A stale source keeps serving its last-good data, so the run stays green.
`--report PATH` writes the issue body, and in Actions the `stale` step
output names the stale sources for the workflow to open, update, or close
the issue.
"""

import argparse
import json
import os
from pathlib import Path

from generator.build import CACHE, SOURCE_KEYS, STALE_AFTER_DAYS, is_stale


def check() -> tuple[list[str], list[str], dict]:
    """Stale sources, sources not refreshed today, and every status."""
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    statuses = cache.get("source_status", {})
    today = cache.get("updated", "")
    stale, behind = [], []
    for key in SOURCE_KEYS:
        status = statuses.get(key, {})
        if is_stale(status, today):
            stale.append(key)
        # Read dates, not state. A run that only flips state skips the cache write.
        elif status.get("last_success") != today:
            behind.append(key)
    return stale, behind, statuses


def report(stale: list[str], statuses: dict) -> str:
    rows = [
        f"These profile sources are past the {STALE_AFTER_DAYS}-day refresh budget.",
        "Their cards keep the last-good data and show when it was last fetched.",
        "",
        "| Source | Last success |",
        "| --- | --- |",
    ]
    for key in stale:
        rows.append(
            f"| {key} | {statuses.get(key, {}).get('last_success') or 'unknown'} |"
        )
    rows += [
        "",
        "The Build profile workflow updates this issue on every run and closes it",
        "once every source is back within budget. See `generator/README.md` for",
        "why a source can't refresh from GitHub-hosted runners.",
    ]
    return "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="write the issue body here")
    args = parser.parse_args(argv)
    stale, behind, statuses = check()
    if behind:
        print(
            f"Not refreshed today, within the {STALE_AFTER_DAYS}-day budget: "
            + ", ".join(behind)
        )
    if stale:
        print("Sources past the refresh budget: " + ", ".join(stale))
    else:
        print(f"All {len(SOURCE_KEYS)} public sources are within the refresh budget.")
    if args.report:
        args.report.write_text(report(stale, statuses), encoding="utf-8")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as out:
            out.write(f"stale={','.join(stale)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
