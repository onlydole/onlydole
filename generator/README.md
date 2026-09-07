# Profile generator

The profile pulls public posts, podcast episodes, GitHub activity, talks,
and books into SVG cards. Python fetches the sources, Jinja renders the
cards, and the build replaces the marked regions in the root `README.md`.
The prose outside those regions stays hand-written.

## Sources

| Card | Source | Ordering |
| --- | --- | --- |
| Writing | [Substack RSS](https://onlydole.substack.com/feed), with the public archive as fallback | Publication date, newest first |
| Attention Deficit | [Podcast RSS](https://attentiondeficitpod.substack.com/feed), with the public archive as fallback | Publication date, newest first |
| Shipped | GitHub public releases and merged public PRs | Merge or publication date, newest first |
| On stage | [Talks feed](https://onlydole.dev/feeds/talks.xml) | Event date, newest first |
| Bookshelf | [Goodreads currently-reading shelf](https://www.goodreads.com/review/list/22801001?shelf=currently-reading) | Update date when available, then shelf-added date |

GitHub activity searches public PRs before applying the result limit.
Filtering a user's latest PRs afterward lets private work crowd out public
work. The query samples 100 public PRs and releases from 50 recently pushed
public repositories; it isn't a complete activity history.

Goodreads doesn't expose Kindle reading progress or last-opened order in
this RSS feed. Its `pubDate` matches the shelf-added date in the observed
feed. The generator requests up to 200 shelf entries and displays three.
An explicit currently-reading shelf takes precedence over an older finished
date, so rereads stay visible. A valid empty shelf clears the displayed books;
an unavailable feed preserves them. A book can stay on that
shelf long after you put it down. Fix that at the source by updating your
Goodreads shelf; a more frequent build cannot recover missing Kindle data.

## Refreshes and failures

The workflow runs every six hours, on generator changes, and on manual
dispatch. Scheduled runs use the default branch and can start late.
Manual runs on a feature branch fetch and validate without publishing;
only runs on `main` can commit generated changes.
The fetch step reads public sources with the workflow token used only for
GitHub. It never needs Goodreads, Kindle, or Substack credentials.

Each successful fetch updates its own `last_success` in
`assets/data-cache.json`. A failed source keeps its last usable data and
last success date. The card and footer label the fallback, and the Actions
job summary lists every source. Old caches without per-source dates show
an unknown last success until the next successful fetch.

The workflow commits successful updates before checking source health.
Any unavailable or cached source then fails the run, so a green check means
all five sources were fetched. RSS has a public Substack archive fallback,
but both endpoints can be blocked by the provider. That remains a failed
refresh, not a successful update of stale content. Both Ubuntu and macOS
hosted runners were blocked by Substack, including a browser-compatible
HTTP client. The final network fallback is [rss2json](https://rss2json.com/docs),
which reads the public feed without an API key. Only the public feed URL is
sent to it. The response must identify the requested publication and link
back to its posts. Relay content can lag the source; an older newest-post
timestamp never replaces a newer snapshot already in the cache. Publication
timestamps are normalized to UTC before sorting, including same-day posts.
The Actions
summary records when the relay was used. If every network route fails,
the build keeps its local cache and fails the source-health check.

Refresh commits use GitHub's GraphQL API for verified signatures, with the
checked-out commit as the expected branch head. A concurrent branch change
prevents an overwrite. Actions are pinned to commit SHAs; Dependabot groups
weekly Action and Python dependency updates.

## Local work

```sh
uv run --locked --project generator pytest tests/ -q
uv run --locked --project generator ruff check generator tests
uv run --locked --project generator ruff format --check generator tests
uv run --locked --project generator python generator/build.py
uv run --locked --project generator python -m generator.health
```

Set `GITHUB_TOKEN` through your environment for live GitHub activity.
Without it, that source uses the cache and the health check fails.
`BUILD_DATE` can set the displayed date for a reproducible fixture build.

Edit the templates and generator, not the generated SVGs. Titles wrap
against the available text width, including the space occupied by book
covers. Extra-long titles end with an ellipsis; full titles and individual
links remain available below each card. SVG clipping is a final boundary,
not the layout algorithm. Check both themes and a narrow viewport after
changing typography. Screens up to 600 pixels wide get separate SVGs with
larger type relative to the image width. Mobile cards omit the cover to leave
more room for titles.

After reviewing an intentional visual change, update the snapshot fixtures:

```sh
uv run --locked --project generator python tests/update_goldens.py
```
