"""Fail a scheduled run when a source has gone past its refresh budget."""

import json

from generator.build import CACHE, SOURCE_KEYS, STALE_AFTER_DAYS, is_stale


def main() -> int:
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    statuses = cache.get("source_status", {})
    today = cache.get("updated", "")
    stale, behind = [], []
    for key in SOURCE_KEYS:
        status = statuses.get(key, {})
        if is_stale(status, today):
            stale.append(key)
        # Dates, not state: a run that only flips state skips the cache write.
        elif status.get("last_success") != today:
            behind.append(key)
    if behind:
        print(
            f"Not refreshed today, within the {STALE_AFTER_DAYS}-day budget: "
            + ", ".join(behind)
        )
    if stale:
        print("Sources past the refresh budget: " + ", ".join(stale))
        return 1
    print(f"All {len(SOURCE_KEYS)} public sources are within the refresh budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
