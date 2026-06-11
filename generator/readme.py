"""Rewrite managed regions of README.md between HTML comment markers."""

import re


class MarkerError(ValueError):
    """Raised when a managed region's markers are missing."""


def replace_region(content: str, name: str, new_body: str) -> str:
    """Replace text between <!-- name:start --> and <!-- name:end -->.

    Markers are preserved. new_body is inserted literally (no regex
    backreference expansion). Raises MarkerError if markers are absent.
    """
    start = f"<!-- {name}:start -->"
    end = f"<!-- {name}:end -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(content):
        raise MarkerError(f"markers for region {name!r} not found")
    return pattern.sub(lambda _m: start + new_body + end, content)
