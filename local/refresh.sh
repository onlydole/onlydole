#!/usr/bin/env bash
# Rebuild the profile from a network Substack answers and commit the result.
#
# Substack blocks GitHub-hosted runners, so the scheduled workflow can't
# refresh the Writing and Podcast cards. This runs the same build against a
# dedicated clone of main and publishes through api_commit.py, so the commit
# is signed by GitHub like the workflow's. Install steps: generator/README.md.
set -euo pipefail

config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/onlydole-profile"
clone="${XDG_STATE_HOME:-$HOME/.local/state}/onlydole-profile/repo"

GITHUB_TOKEN="$(<"$config_dir/github-token")"
READWISE_BOOKS_TOKEN="$(<"$config_dir/readwise-books-token")"
export GITHUB_TOKEN READWISE_BOOKS_TOKEN
export GITHUB_REPOSITORY="onlydole/onlydole" GITHUB_REF_NAME="main"
export PYTHONUNBUFFERED=1

if [[ ! -d "$clone/.git" ]]; then
	git clone --quiet "https://github.com/$GITHUB_REPOSITORY.git" "$clone"
fi
cd "$clone"

# A second attempt covers the workflow committing while this run built.
for attempt in 1 2; do
	git fetch --quiet origin "$GITHUB_REF_NAME"
	git reset --quiet --hard "origin/$GITHUB_REF_NAME"
	git clean --quiet -fd -- assets
	uv run --locked --project generator python generator/build.py
	if uv run --locked --project generator python generator/api_commit.py; then
		exit 0
	fi
	echo "commit attempt $attempt failed" >&2
done
exit 1
