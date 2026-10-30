import json

import pytest

from generator import build, health

FRESH = {
    key: {"state": "fresh", "last_success": "2026-06-10"} for key in build.SOURCE_KEYS
}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    path = tmp_path / "cache.json"
    monkeypatch.setattr(health, "CACHE", path)

    def write(statuses, updated="2026-06-10"):
        path.write_text(json.dumps({"source_status": statuses, "updated": updated}))

    return write


def test_health_passes_when_every_source_is_fresh(cache):
    cache(FRESH)
    assert health.main([]) == 0


def test_health_tolerates_a_recent_cache(cache, capsys):
    cache({**FRESH, "writing": {"state": "cached", "last_success": "2026-06-09"}})
    assert health.main([]) == 0
    assert "within the 1-day budget: writing\n" in capsys.readouterr().out


def test_health_reports_past_the_budget_without_failing(cache, capsys):
    cache({**FRESH, "podcast": {"state": "cached", "last_success": "2026-06-08"}})
    assert health.main([]) == 0
    assert "past the refresh budget: podcast" in capsys.readouterr().out


def test_health_counts_missing_or_unknown_status_as_stale(cache):
    cache({**FRESH, "writing": {"state": "cached"}})
    assert health.check()[0] == ["writing"]
    cache({})
    assert health.check()[0] == list(build.SOURCE_KEYS)


def test_health_reports_the_source_count(cache, capsys):
    cache(FRESH)
    health.main([])
    assert f"All {len(build.SOURCE_KEYS)} public sources" in capsys.readouterr().out


def test_health_writes_the_issue_body_and_step_output(cache, tmp_path, monkeypatch):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    cache(
        {
            **FRESH,
            "writing": {"state": "cached", "last_success": "2026-06-01"},
            "reading": {"state": "unavailable", "last_success": None},
        }
    )
    report = tmp_path / "health.md"
    assert health.main(["--report", str(report)]) == 0
    body = report.read_text(encoding="utf-8")
    assert "| writing | 2026-06-01 |\n" in body
    assert "| reading | unknown |\n" in body
    assert "podcast" not in body
    assert output.read_text(encoding="utf-8") == "stale=writing,reading\n"


def test_health_step_output_is_empty_when_every_source_is_fresh(
    cache, tmp_path, monkeypatch
):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    cache(FRESH)
    assert health.main([]) == 0
    assert output.read_text(encoding="utf-8") == "stale=\n"
