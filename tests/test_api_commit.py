from generator.api_commit import _stale_data_only, plan_changes


def test_plan_changes_maps_modified_added_and_deleted():
    porcelain = "\0".join(
        [
            " M README.md",
            " M assets/hero-light.svg",
            " D assets/old-tile.svg",
            "?? assets/new tile.svg",
            "",
        ]
    )
    changes = plan_changes(porcelain)
    assert {a["path"] for a in changes["additions"]} == {
        "README.md",
        "assets/hero-light.svg",
        "assets/new tile.svg",
    }
    assert changes["deletions"] == [{"path": "assets/old-tile.svg"}]


def test_plan_changes_splits_a_rename_into_add_and_delete():
    changes = plan_changes("R  assets/hero-light.svg\0assets/hero.svg\0")
    assert changes == {
        "additions": [{"path": "assets/hero-light.svg"}],
        "deletions": [{"path": "assets/hero.svg"}],
    }


def test_plan_changes_empty_output_means_no_changes():
    assert plan_changes("") == {"additions": [], "deletions": []}
    assert plan_changes("\0") == {"additions": [], "deletions": []}


def test_stale_data_only_detects_pure_stale_data():
    assert _stale_data_only([{"type": "STALE_DATA", "message": "Expected ..."}])
    assert not _stale_data_only(
        [{"type": "STALE_DATA"}, {"type": "FORBIDDEN", "message": "nope"}]
    )
    assert not _stale_data_only([])
    assert not _stale_data_only([{"message": "no type field"}])
