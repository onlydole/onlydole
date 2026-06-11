from generator.api_commit import _stale_data_only, plan_changes


def test_plan_changes_maps_modified_added_and_deleted():
    porcelain = (
        " M README.md\n"
        " M assets/hero.svg\n"
        " D assets/old-tile.svg\n"
        "?? assets/new-tile.svg\n"
    )
    changes = plan_changes(porcelain)
    assert {a["path"] for a in changes["additions"]} == {
        "README.md",
        "assets/hero.svg",
        "assets/new-tile.svg",
    }
    assert changes["deletions"] == [{"path": "assets/old-tile.svg"}]


def test_plan_changes_empty_output_means_no_changes():
    assert plan_changes("") == {"additions": [], "deletions": []}
    assert plan_changes("\n") == {"additions": [], "deletions": []}


def test_stale_data_only_detects_pure_stale_data():
    assert _stale_data_only([{"type": "STALE_DATA", "message": "Expected ..."}])
    assert not _stale_data_only(
        [{"type": "STALE_DATA"}, {"type": "FORBIDDEN", "message": "nope"}]
    )
    assert not _stale_data_only([])
    assert not _stale_data_only([{"message": "no type field"}])
