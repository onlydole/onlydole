import json

from generator import health


def test_health_requires_every_source_to_be_fresh(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    monkeypatch.setattr(health, "CACHE", cache)
    statuses = {
        key: {"state": "fresh"}
        for key in ("writing", "podcast", "shipped", "stage", "reading")
    }
    cache.write_text(json.dumps({"source_status": statuses}))
    assert health.main() == 0
    statuses["writing"]["state"] = "cached"
    cache.write_text(json.dumps({"source_status": statuses}))
    assert health.main() == 1
    cache.write_text("{}")
    assert health.main() == 1
