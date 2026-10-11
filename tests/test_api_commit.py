import base64

import pytest

from generator import api_commit
from generator.api_commit import _stale_data_only, plan_changes


def test_plan_changes_maps_modified_added_and_deleted():
    porcelain = (
        " M README.md\0"
        " M assets/hero-light.svg\0"
        " D assets/old-tile.svg\0"
        "?? assets/new tile.svg\0"
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


class _Response:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(api_commit, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_REPOSITORY", "onlydole/onlydole")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    answers = {"status": " M README.md\0 D assets/old.svg\0", "rev-parse": "abc123\n"}
    monkeypatch.setattr(api_commit, "_git", lambda *args: answers[args[0]])
    return tmp_path


def _post(monkeypatch, body):
    sent = []

    def post(url, **kwargs):
        sent.append(kwargs["json"])
        return _Response(body)

    monkeypatch.setattr(api_commit.httpx, "post", post)
    return sent


def test_main_commits_against_the_checked_out_head(checkout, monkeypatch):
    commit = {"oid": "def4567890", "url": "https://github.com/c"}
    sent = _post(monkeypatch, {"data": {"createCommitOnBranch": {"commit": commit}}})
    assert api_commit.main() == 0
    (payload,) = sent
    request = payload["variables"]["input"]
    assert request["expectedHeadOid"] == "abc123"
    assert request["branch"] == {
        "repositoryNameWithOwner": "onlydole/onlydole",
        "branchName": "main",
    }
    assert request["fileChanges"] == {
        "additions": [
            {"path": "README.md", "contents": base64.b64encode(b"hello").decode()}
        ],
        "deletions": [{"path": "assets/old.svg"}],
    }


def test_main_fails_when_main_moved_after_checkout(checkout, monkeypatch):
    _post(monkeypatch, {"errors": [{"type": "STALE_DATA"}]})
    assert api_commit.main() == 1


def test_main_skips_the_api_when_nothing_changed(checkout, monkeypatch):
    monkeypatch.setattr(api_commit, "_git", lambda *args: "")
    sent = _post(monkeypatch, {})
    assert api_commit.main() == 0
    assert sent == []
