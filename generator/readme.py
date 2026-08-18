"""Rewrite managed regions of README.md between HTML comment markers."""

import re


class MarkerError(ValueError):
    """Raised when a managed region's markers are missing."""


def replace_region(content: str, name: str, new_body: str) -> str:
    """Replace text between <!-- name:start --> and <!-- name:end -->.

    Markers are preserved. new_body is inserted literally (no regex
    backreference expansion). Raises MarkerError unless exactly one ordered
    marker pair is present.
    """
    start = f"<!-- {name}:start -->"
    end = f"<!-- {name}:end -->"
    start_count = content.count(start)
    end_count = content.count(end)
    if start_count != 1 or end_count != 1:
        raise MarkerError(
            f"expected exactly one marker pair for region {name!r}; "
            f"found {start_count} start and {end_count} end markers"
        )
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(content):
        raise MarkerError(f"markers for region {name!r} are out of order")
    return pattern.sub(lambda _m: start + new_body + end, content, count=1)
