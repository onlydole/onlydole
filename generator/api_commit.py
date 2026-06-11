"""Create the dashboard refresh commit on GitHub via GraphQL.

Plain `git push` from Actions is rejected by the repository ruleset that
requires verified commit signatures on main. Commits created with the
GraphQL `createCommitOnBranch` mutation are signed by GitHub automatically,
so the daily refresh satisfies the rule without managing signing keys.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPHQL_URL = "https://api.github.com/graphql"
TRACKED_PATHS = ("README.md", "assets/")
COMMIT_HEADLINE = "chore: refresh profile dashboard"

MUTATION = """
mutation ($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid url }
  }
}
"""


def plan_changes(porcelain: str) -> dict:
    """Map `git status --porcelain` output to GraphQL fileChanges.

    Paths are assumed not to contain spaces or quoting (true for this
    repo's README.md and assets/*.svg outputs).
    """
    additions: list[dict] = []
    deletions: list[dict] = []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        status, path = line[:2], line[3:].strip()
        if status.strip().startswith("D"):
            deletions.append({"path": path})
        else:
            additions.append({"path": path})
    return {"additions": additions, "deletions": deletions}


def _stale_data_only(errors: list[dict]) -> bool:
    """True when every error is STALE_DATA — i.e. another run already
    committed and moved the branch, so there is nothing left to do."""
    return bool(errors) and all(e.get("type") == "STALE_DATA" for e in errors)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def main() -> int:
    changes = plan_changes(_git("status", "--porcelain", "--", *TRACKED_PATHS))
    if not (changes["additions"] or changes["deletions"]):
        print("no changes to commit")
        return 0
    for addition in changes["additions"]:
        raw = (REPO_ROOT / addition["path"]).read_bytes()
        addition["contents"] = base64.b64encode(raw).decode()
    payload = {
        "query": MUTATION,
        "variables": {
            "input": {
                "branch": {
                    "repositoryNameWithOwner": os.environ["GITHUB_REPOSITORY"],
                    "branchName": os.environ.get("GITHUB_REF_NAME", "main"),
                },
                "message": {"headline": COMMIT_HEADLINE},
                "expectedHeadOid": _git("rev-parse", "HEAD").strip(),
                "fileChanges": changes,
            }
        },
    }
    resp = httpx.post(
        GRAPHQL_URL,
        json=payload,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"},
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        if _stale_data_only(body["errors"]):
            print("branch advanced during run; a concurrent refresh already landed")
            return 0
        print(f"error: {body['errors']}", file=sys.stderr)
        return 1
    commit = body["data"]["createCommitOnBranch"]["commit"]
    print(f"created signed commit {commit['oid'][:9]}: {commit['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
