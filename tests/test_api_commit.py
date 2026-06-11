from generator.api_commit import plan_changes


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
