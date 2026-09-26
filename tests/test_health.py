import json

import pytest

from generator import build, health

FRESH = {key: {"state": "fresh"} for key in build.SOURCE_KEYS}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    monkeypatch.setattr(health, "CACHE", path)

    def write(statuses, updated="2026-06-10"):
        path.write_text(json.dumps({"source_status": statuses, "updated": updated}))

    return write


def test_health_passes_when_every_source_is_fresh(cache):
    cache(FRESH)
    assert health.main() == 0


def test_health_tolerates_a_recent_cache(cache, capsys):
    cache({**FRESH, "writing": {"state": "cached", "last_success": "2026-06-09"}})
    assert health.main() == 0
    assert "within the 1-day budget: writing" in capsys.readouterr().out


def test_health_fails_past_the_budget(cache, capsys):
    cache({**FRESH, "podcast": {"state": "cached", "last_success": "2026-06-08"}})
    assert health.main() == 1
    assert "past the refresh budget: podcast" in capsys.readouterr().out


def test_health_fails_on_missing_or_unknown_status(cache):
    cache({**FRESH, "writing": {"state": "cached"}})
    assert health.main() == 1
    cache({})
    assert health.main() == 1


def test_health_reports_the_source_count(cache, capsys):
    cache(FRESH)
    health.main()
    assert f"All {len(build.SOURCE_KEYS)} public sources" in capsys.readouterr().out
