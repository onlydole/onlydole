# Profile README Redesign — "The Bento Dashboard"

**Date:** 2026-06-10
**Repo:** onlydole/onlydole (GitHub special profile repository)
**Status:** Approved design, pending implementation plan

## Goal

Replace the static profile README with a **living dashboard**: a custom-designed
bento grid of self-generated SVG tiles that auto-refresh daily via GitHub
Actions. Zero third-party widget services. The profile should signal "this
person is active, ships, writes, and speaks" the moment it loads — and prove it
with content that is never stale.

## Decisions made (with Taylor)

| Decision | Choice |
|---|---|
| Primary job of the profile | Living dashboard (auto-updating showcase) |
| Content sources | Substack posts, GitHub activity, talks & appearances, currently reading |
| Design direction | Bento — custom self-generated SVG tile grid |
| Composition | Hero-led: full-width identity tile, 2×2 content tiles, connect strip |
| Palette | "LA Sunset" — coral → magenta → violet gradient hero, warm accents |
| Generator language | Python (uv-managed; feedparser, httpx, PyYAML, Jinja2) |
| Hero click destination | https://onlydole.dev |

Retired from the current README: typing SVG, skillicons grid, any third-party
stat widgets. Explicitly out of scope: contribution snake, follower-funnel CTAs
(the closed PR #35 approach), Goodreads/Literal integration (reading is a
manually edited YAML for now), GIF/video content.

## Part 1 — The Artifact (what visitors see)

### Page structure (top to bottom)

1. **Hero tile** — full-width SVG, LA Sunset gradient (`#7c2d4f → #c2414f →
   #e8702a`). Content: "Taylor Dolezal" (large), role line "Head of Open Source
   @ Dosu · CNCF Ambassador · Los Angeles", credibility line "KubeCon keynoter ·
   ex-Disney Studios SRE · ex-HashiCorp". Subtle CSS gradient shimmer animation
   inside the SVG (works when embedded as `<img>`; must be tasteful and slow).
   Wrapped in a link to `https://onlydole.dev`. The hero is identical in dark
   and light themes (it carries its own background).

2. **Content tiles** — 2×2 grid; each tile is one SVG, one click target:

   | Tile | Content | Items | Tile links to |
   |---|---|---|---|
   | ✍️ Latest Writing | Substack RSS | 3 newest posts: title + date | Newest post URL |
   | 🔨 Recently Shipped | GitHub GraphQL | 3 newest of (releases ∪ merged PRs) | Newest item URL |
   | 🎤 On Stage | `data/talks.yaml` | 3 latest entries (fewer if the file has fewer): title + venue + date | Newest entry URL |
   | 📚 Reading Now | `data/reading.yaml` | Current book: title + author + optional one-line note | Book URL (optional; falls back to no link) |

3. **Connect strip** — four small self-generated SVG chips, each its own link:
   Substack (`https://onlydole.substack.com`), LinkedIn
   (`https://www.linkedin.com/in/onlydole`), Bluesky
   (`https://bsky.app/profile/onlydole.dev`), Website (`https://onlydole.dev`).

4. **Short About** — plain markdown, ~3 sentences (searchable, screen-reader
   friendly). Draft text:

   > I've spent my career refactoring complex systems into intuitive platforms —
   > running production at Disney Studios, developer advocacy at HashiCorp,
   > stewarding the end-user ecosystem at CNCF, and now leading open source at
   > Dosu. I care about the humans behind the code: maintainers, newcomers, and
   > the communities that keep this ecosystem thriving. Reach out about
   > Kubernetes, AI infrastructure, open source — or the best hikes in LA.

5. **Freshness stamp** — tiny footer line `Last refreshed: YYYY-MM-DD`,
   rewritten on every build.

### Rendering constraints (the rules of the medium)

- GitHub proxies README images through camo and strips interactivity: **links
  inside an SVG do not work**. Therefore each tile is one SVG wrapped in one
  markdown/HTML link. Per-line links inside tiles are not attempted.
- SVGs embedded via `<img>` cannot load external fonts. All text uses a system
  font stack: `-apple-system, 'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif`.
- Dark/light theming via GitHub's supported `<picture>` element:
  `<source media="(prefers-color-scheme: dark)" srcset="assets/tile-dark.svg">`
  with the light variant as the `<img>` fallback. Tiles and chips get two
  variants; the hero ships one self-contained SVG.
- Side-by-side layout: tile images placed two-up with `width="49%"`; GitHub
  stacks them on narrow viewports. Acceptance criterion is visual (2-up on
  desktop, stacked on mobile), exact markup may be tuned during implementation.
- Camo caches images for minutes-to-hours; with a daily refresh cadence this is
  acceptable and requires no cache-busting tricks.

### Palette tokens (starting values, tunable during visual QA)

| Token | Dark variant | Light variant |
|---|---|---|
| Tile background | `#1a1417` | `#fff6f0` |
| Tile border | `#463038` | `#f3ddd0` |
| Header accent | `#ff9d76` | `#c2414f` |
| Body text | `#e6ddd9` | `#44322e` |
| Muted text | `#a08a84` | `#8a6f66` |
| Hero gradient | `#7c2d4f → #c2414f → #e8702a` (both themes) | same |

### Accessibility

- Every image gets regenerated alt text containing the actual content, e.g.
  `alt="Latest writing: The maintainer's dilemma — Jun 8; AI eats the SBOM — Jun 1; …"`.
- The About section and connect chips ensure name, role, and all destinations
  exist as real text/links for screen readers and search.

## Part 2 — The Machine (how it stays alive)

### Repo layout

```
README.md                  # static frame + two managed regions (bento block, stamp)
data/
  talks.yaml               # append an entry per talk/podcast/panel
  reading.yaml             # edit when the current book changes
generator/
  build.py                 # entrypoint: fetch → render → write README regions
  templates/*.svg.j2       # Jinja2 SVG templates: hero, tiles, chips (dark+light)
  pyproject.toml           # uv-managed deps: feedparser, httpx, PyYAML, Jinja2
assets/*.svg               # generated output, committed (e.g. writing-dark.svg, writing-light.svg)
tests/                     # pytest: golden-file SVG tests, parser fixtures
.github/workflows/
  build-profile.yml        # daily heartbeat (new)
  ci.yml                   # pytest on pull requests (new)
  superlinter.yml          # kept; action pins bumped (covers closed Dependabot #34)
  linkchecker.yml          # kept; action pins bumped (covers closed Dependabot #33)
lychee.toml                # exclude generated asset paths and rate-limited hosts
.gitignore                 # .superpowers/, __pycache__/, .venv/, .DS_Store
```

### Data schemas

`data/talks.yaml` — list, newest first or any order (script sorts by date desc):

```yaml
- title: "Keynote: <talk title>"
  venue: "KubeCon + CloudNativeCon EU"
  date: 2026-04-02
  url: "https://www.youtube.com/watch?v=..."
  kind: keynote   # keynote | talk | podcast | panel
```

`data/reading.yaml`:

```yaml
current:
  title: "Thinking in Systems"
  author: "Donella Meadows"
  url: ""        # optional
  note: ""       # optional one-liner shown under the title
```

### `build.py` behavior

1. Load YAML data; fetch Substack RSS (`https://onlydole.substack.com/feed`);
   query GitHub GraphQL as `user(login: "onlydole")` for latest releases on
   public owned repos and latest merged public PRs authored by Taylor
   (excluding the profile repo itself); merge, sort by date desc, take 3.
   Uses the workflow's built-in `GITHUB_TOKEN` — public data only, no PAT.
2. Render every SVG from Jinja2 templates with XML-escaped, length-truncated
   text (ellipsis on overflow; truncation widths defined per template).
3. Rewrite the README's two managed regions, delimited by HTML comment markers
   (`<!-- bento:start -->…<!-- bento:end -->` and
   `<!-- stamp:start -->…<!-- stamp:end -->`): image embeds with fresh alt
   text and link targets, and the freshness stamp. Static prose outside the
   markers is never touched.
4. **Per-source failure isolation:** if a source fails (network error, malformed
   feed, API error), skip re-rendering that tile — its committed SVG and its
   README alt text stay at last-good state. Log a warning, continue with the
   healthy sources, exit 0. A wholesale failure (all sources down) still exits 0
   with everything untouched.
5. The build receives "now" as an injected value so templates stay
   deterministic and golden-testable.

### `build-profile.yml` (the heartbeat)

- **Triggers:** `schedule: cron "17 8 * * *"` (odd minute, off-peak),
  `workflow_dispatch`, and `push` to `main` filtered to paths `data/**`,
  `generator/**`.
- **Steps:** checkout → install uv + deps → run `build.py` → commit-and-push
  only if changed (`git diff --quiet || git commit …`) using the
  `github-actions[bot]` identity.
- **Hardening:** `permissions: contents: write` and nothing more; all actions
  pinned to released versions that exist; a `concurrency` group prevents
  overlapping runs; no untrusted event data is interpolated into `run:` steps.

### Quality gates

- `ci.yml` runs pytest on PRs: golden-file tests (fixture data → rendered SVGs
  byte-compare against checked-in goldens) plus parser tests against RSS and
  GraphQL response fixtures and YAML schema validation.
- In scheduled runs, malformed YAML is treated as a source failure (tile keeps
  last-good content); in CI, the same condition fails the test suite loudly.
- super-linter keeps the relaxed markdownlint profile needed for a rich profile
  README (`MD013`, `MD033`, `MD034` off), salvaged from closed PR #35.
- lychee link checking continues weekly; generated asset paths and the
  rate-limit-prone hosts are excluded.

## Acceptance criteria

1. Profile renders the hero, 2×2 tiles, chips, About, and stamp — 2-up on
   desktop, stacked on mobile, correct in both dark and light themes.
2. All click targets work: hero → onlydole.dev, each tile → its newest item,
   each chip → its destination.
3. A new Substack post appears on the profile after the next daily build with
   no manual action (≤24h to build, plus GitHub's image-cache expiry of
   minutes-to-hours); `workflow_dispatch` refreshes on demand.
4. Killing any one data source leaves that tile showing last-good content and
   does not block other tiles from updating.
5. All four workflows are green; no third-party runtime service appears
   anywhere in the rendered profile.
6. Repo is forkable: another user could swap names/feeds in one config spot and
   regenerate (nice-to-have, not a blocker).

## Risks & mitigations

- **Substack feed shape changes** → parser tests with a checked-in fixture;
  failure isolation keeps the tile at last-good.
- **GraphQL rate limits / token scope surprises** → public-data queries with
  `GITHUB_TOKEN`; failure isolation as backstop.
- **SVG looks different in GitHub's sanitizer than in a browser** → visual QA
  on a draft PR before merge; goldens lock the markup once approved.
- **Maintenance burden** (the known cost of the Bento) → small, single-purpose
  Python module with tests; talks/reading updates are one-line YAML edits.
