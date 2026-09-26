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
public repositories; it isn't a complete activity history. PRs and
releases from this profile repository are left out of both.

Goodreads doesn't expose Kindle reading progress or last-opened order in
this RSS feed. Its `pubDate` matches the shelf-added date in the observed
feed. The generator requests up to 200 shelf entries and displays three.
An explicit currently-reading shelf takes precedence over an older finished
date, so rereads stay visible. A valid empty shelf clears the displayed books;
an unavailable feed preserves them. A book can stay on that
shelf long after you put it down. Fix that at the source by updating your
Goodreads shelf; a more frequent build cannot recover missing Kindle data.

## Motion

The hero draws the career as a commit graph. `main` carries the day jobs,
Disney Studios through Dosu. An `upstream` lane forks after the first stop,
carries the Kubernetes and community work as tags, and merges into `main`
at HEAD, where the community work became the job. On phones the graph
stacks top to bottom and a legend names the upstream commits. After the
graph draws, only the HEAD marker's pulse and the sun's glow keep moving.

The cards take turns. After the page loads, one card at a time plays a
short gesture tied to its source. The document rewrites its lines, the
headphones show a voice meter, the branch merges, the microphone
broadcasts, and the book turns a page or catches light on its cover. Three
sweeps play down the page, then the cards rest.

The templates follow four rules, and `tests/test_render.py` checks them.

- Every animation runs from a hidden or partial state back to the
  element's own SVG attributes. Nothing uses `forwards` or `both`, so a
  renderer without animation shows the finished drawing.
- Motion is opt-in. Every animation rule sits inside
  `@media (prefers-reduced-motion: no-preference)`, and elements carry only
  their timing as CSS variables, so a visitor who asks for reduced motion,
  or a renderer that can't tell, gets the still drawing.
- Copy never starts hidden. Only the career graph's labels enter with
  their stops, and the alt text carries every one of them.
- No `feTurbulence` or other expensive filters. An animated SVG image
  repaints every frame.

`layout.py` computes geometry and timing, so templates only loop over
prepared values. The career, the upstream tags, the mission's line breaks,
and the tagline live in `HERO` in `build.py`. The alt text is built from
the same data, so the picture and its description can't drift apart.

The hero is paper in light mode and the same city at night in dark mode.
The dark variant inverts the illustration's lightness and rotates its hue
back, so the ink turns pale and the sun keeps its color. The profile page
offers four hero files, phone layouts first, and GitHub picks by viewport
width and `prefers-color-scheme`. The illustration is embedded as WebP, which cut
each hero from 418 KB to about 107 KB.

The build owns every SVG in `assets/`. Each run deletes SVGs it didn't
write, so renamed or retired cards don't linger.

## Refreshes and failures

The workflow runs every six hours, on generator changes, and on manual
dispatch. Scheduled runs use the default branch and can start late.
Manual runs on a feature branch fetch and validate without publishing;
only runs on `main` can commit generated changes.
The fetch step reads public sources with the workflow token used only for
GitHub. It never needs Goodreads, Kindle, or Substack credentials.

Each successful fetch updates its own `last_success` in
`assets/data-cache.json`. A failed source keeps its last usable data and
last success date. Old caches without per-source dates show an unknown
last success until the next successful fetch, and count as stale.

The workflow commits successful updates before checking source health.
Health is a staleness budget, not a per-run check. A source may serve its
cache for one calendar day (UTC) without failing the run or labeling the
card. Once its last success is older than yesterday, the card and footer
name the outage and the scheduled run fails. `STALE_AFTER_DAYS` in
`build.py` sets the budget, and the Actions job summary lists every source
on every run.

The budget exists because of Substack. It blocks Ubuntu and macOS hosted
runners on both the RSS feed and the public archive, including a
browser-compatible HTTP client. Both Substack cards therefore depend on
[rss2json](https://rss2json.com/docs), a free relay that reads the public
feed without an API key. Only the public feed URL is sent to it. The
response must identify the requested publication and link back to its
posts. The relay answers 500 on roughly one run in four, and before the
budget each of those turned the scheduled run red while the card was at
most six hours behind.

Every source request retries 429 and 5xx answers and dropped connections
twice, after 2 and 5 seconds. A 4xx such as Substack's 403 is a policy
answer and fails at once, and timeouts aren't retried. Relay content can
lag the source. An older newest-post timestamp never replaces a newer
snapshot already in the cache. Publication timestamps are normalized to
UTC before sorting, including same-day posts. The Actions summary records
when the relay was used. If every network route fails, the build keeps
its local cache.

Refresh commits use GitHub's GraphQL API for verified signatures, with the
checked-out commit as the expected branch head. A concurrent branch change
prevents an overwrite. Actions are pinned to commit SHAs; Dependabot groups
weekly Action and Python dependency updates.

## Local work

```sh
uv run --locked --project generator pytest tests/ -q
uv run --locked --project generator ruff check .
uv run --locked --project generator ruff format --check .
uv run --locked --project generator python generator/build.py
uv run --locked --project generator python -m generator.health
```

Set `GITHUB_TOKEN` through your environment for live GitHub activity.
Without it, that source uses the cache and counts toward the staleness budget.
`BUILD_DATE` can set the displayed date for a reproducible fixture build.

Edit the templates and generator, not the generated SVGs. Titles wrap
against the available text width, including the space occupied by book
covers. Extra-long titles end with an ellipsis; full titles and individual
links remain available below each card. SVG clipping is a final boundary,
not the layout algorithm. Check both themes and a narrow viewport after
changing typography, and check reduced motion after changing animation.
Activity cards use one wide, shallow layout at every viewport so GitHub
cannot substitute a taller card with oversized type. The hero retains its
separate mobile layout.

After reviewing an intentional visual change, update the snapshot fixtures.
The script also deletes snapshots that no longer have a case.

```sh
uv run --locked --project generator python tests/update_goldens.py
```
