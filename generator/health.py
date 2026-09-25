"""Fail a scheduled run when a source has gone past its refresh budget."""

import json

from generator.build import CACHE, STALE_AFTER_DAYS, is_stale

EXPECTED = ("podcast", "reading", "shipped", "stage", "writing")


def main() -> int:
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    statuses = cache.get("source_status", {})
    today = cache.get("updated", "")
    stale, cached = [], []
    for key in EXPECTED:
        status = statuses.get(key, {})
        if is_stale(status, today):
            stale.append(key)
        elif status.get("state") != "fresh":
            cached.append(key)
    if cached:
        print(
            f"Serving cache within the {STALE_AFTER_DAYS}-day budget: "
            + ", ".join(cached)
        )
    if stale:
        print("Sources past the refresh budget: " + ", ".join(stale))
        return 1
    print("All five public sources are within the refresh budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
