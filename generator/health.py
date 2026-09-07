"""Fail a scheduled run when any source could not be refreshed."""

import json

from generator.build import CACHE


def main() -> int:
    statuses = json.loads(CACHE.read_text(encoding="utf-8")).get("source_status", {})
    expected = {"writing", "podcast", "shipped", "stage", "reading"}
    failed = [
        key for key in sorted(expected) if statuses.get(key, {}).get("state") != "fresh"
    ]
    if failed:
        print("Sources not refreshed: " + ", ".join(failed))
        return 1
    print("All five public sources refreshed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
