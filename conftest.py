import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def _no_retry_wait(monkeypatch):
    """Keep retry backoff out of the test run."""
    from generator import sources

    monkeypatch.setattr(sources, "_sleep", lambda _seconds: None)
