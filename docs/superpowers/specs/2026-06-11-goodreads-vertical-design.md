# Goodreads Reading Tile + Vertical Full-Width Layout

**Date.** 2026-06-11
**Repo.** onlydole/onlydole
**Status.** Approved design, pending implementation plan
**Builds on.** `2026-06-10-profile-readme-design.md` (the bento dashboard)

## Goal

Two changes to the live bento dashboard. First, the Reading Now tile becomes
fully automated, sourced from Taylor's public Goodreads currently-reading
shelf, with the real book cover embedded. Second, the four content tiles move
from a 2×2 grid of 600px tiles to stacked full-width rows (1200px), which
eliminates the title truncation visible today (titles were cut at 40
characters and the live stage tile shows mid-word ellipses).

## Decisions made (with Taylor)

| Decision | Choice |
|---|---|
| Reading source | Goodreads RSS, user id `22801001`, shelf `currently-reading` |
| Integration shape | Direct fetch in the generator (`fetch_goodreads()` in sources.py), no third-party actions, no secrets |
| Layout | "Roomy rows". Full-width stacked tiles, two-line entries (title line, muted detail line) |
| Book cover | Embedded as base64 data URI in the reading row SVG, first book only, with graceful text-only fallback |
| `data/reading.yaml` | Retired and deleted |
| Books shown | Up to 3 from the shelf |
| Reading row link | First book's Goodreads page |
| Attribution | Small "via Goodreads" credit in the reading row header |
| Truncation budgets | Titles 92 chars (was 40), detail lines 110 (was 52) |

## Part 1 — The Artifact

### Layout change (all four tiles)

- Tile SVGs become full-width rows. `viewBox` width 1200 (same as hero),
  height computed from content. Formula `height = 88 + 74 * line_count + 26`,
  where a "line" is one entry (primary + secondary text pair). The reading
  row uses `max(formula, 250)` when a cover is present so the cover fits.
- The README bento block stacks each tile `<picture>` at `width="100%"`,
  one per line, replacing the two-up pairs. Hero and connect chips are
  unchanged. Tile order stays writing, shipped, on stage, reading.
- Entry typography keeps the current sizes (25px primary, 17px secondary,
  same palette tokens). Exact spacing may be tuned during visual QA.
- `fit()` budgets rise to 92 (primary) and 110 (secondary). The ellipsis
  remains as a safety net only.

### Reading row (Goodreads-powered)

- Lists up to 3 books from the currently-reading shelf. Each book renders
  as primary = title (fit 92), secondary = author name.
- The first book's cover renders at the left of the row, approximately
  92px wide (aspect preserved), from the feed's large image variant,
  embedded as a base64 data URI. Text block shifts right when the cover
  is present.
- Header reads `📚 READING NOW · via Goodreads` with the credit in muted
  styling.
- The row links to the first book's Goodreads page (the feed's `link`
  value). Alt text lists every shown title and author.
- With no cover available the row renders text-only with the original
  left margin. With an empty shelf the row falls back to cached data,
  then to the quiet "—" empty state.

## Part 2 — The Machine

### New source (`generator/sources.py`)

- `GOODREADS_USER_ID = "22801001"` and
  `GOODREADS_FEED = "https://www.goodreads.com/review/list_rss/22801001?shelf=currently-reading"`.
- `parse_goodreads(feed_text) -> list[dict]` returns up to 3 of
  `{"title", "author", "url", "image_url"}`. Title from `<title>`, author
  from `<author_name>`, url from `<link>` (the review/book link), image
  from `<book_large_image_url>` falling back to `<book_image_url>`.
- Parser choice (feedparser vs stdlib `xml.etree.ElementTree`) is settled
  during implementation by whichever cleanly surfaces the custom Goodreads
  elements against a checked-in fixture. The fixture is real feed shape
  captured 2026-06-11.
- `fetch_goodreads()` wraps the HTTP call (httpx, 30s timeout, explicit
  User-Agent header since Goodreads rejects some default agents) and
  raises `SourceError` on any failure, matching the other sources.
- `load_reading()` and `data/reading.yaml` are deleted, along with their
  tests. `talks.yaml` stays (talks have no feed anywhere).

### Cover pipeline (`generator/build.py`)

- After a successful Goodreads fetch, the build downloads the first book's
  `image_url`. Rules. Reuse the cached base64 when the cached cover URL
  matches (no daily re-download). Cap the download at 80KB, skipping the
  cover beyond that. Any cover failure degrades to text-only rendering
  without failing the build or touching the books data.
- `data-cache.json` schema for the reading key becomes
  `{"books": [...], "cover": {"url": ..., "b64": ..., "mime": ...}}`.
  The cache write happens exactly as today.
- Migration. A cached reading entry in the old YAML-era shape (a dict
  with `title`/`author` keys instead of `books`) is treated as absent.
  The first successful fetch overwrites it with the new shape.

### Template and embed changes

- `tile.svg.j2` gains `width`/`height` parameters and an optional `cover`
  block (image element with the data URI, text x-offset shifts when
  present). Golden fixtures regenerate for the wide geometry, including
  one cover variant and one text-only variant.
- `bento_html()` emits stacked full-width `<picture>` embeds. The reading
  row's `<a>` wraps as before (or no link when the shelf and cache are
  both empty).

### Failure isolation (unchanged in shape)

| Failure | Behavior |
|---|---|
| Goodreads HTTP/parse failure | `SourceError`, cached books + cached cover render |
| Cover download fails or exceeds 80KB | Books render text-only, build succeeds |
| Empty shelf | Cached books, else "—" empty state |
| Everything down | Whole tile stays at last-good state, build exits 0 |

## Testing

- New fixture `tests/fixtures/goodreads.xml` (two books, real shape).
- Parser tests. Three-book cap, field extraction, image fallback order,
  garbage input raises `SourceError`.
- Cover tests. Cache-hit skips download, size cap skips cover, failure
  degrades to text-only (monkeypatched httpx).
- Golden updates for wide tiles (with and without cover).
- Build end-to-end updated for the stacked README markup and the new
  reading flow. Suite target is every test green with no network access.

## Acceptance criteria

1. No ellipsis appears for any title up to 92 characters. The three live
   talk titles and the current book title render whole.
2. The profile renders hero, four full-width rows, chips, About, stamp,
   correct in dark and light themes.
3. The reading row shows the real current book, author, cover, and links
   to its Goodreads page, refreshed by the daily build with no manual step.
4. Killing the Goodreads feed leaves the row at last-good content.
5. All workflows stay green. No new dependencies, secrets, or third-party
   runtime services.
6. `data/reading.yaml` is gone and nothing references it.

## Risks

- **Goodreads feed drift or bot-blocking.** Explicit User-Agent, fixture
  tests, and the cache backstop. Worst case the row freezes at last-good.
- **Cover bytes bloat the repo.** 80KB cap, single cover, base64 stored in
  one cache file and one SVG. History growth is bounded and acceptable.
- **Wide-tile typography looks off at first render.** Visual QA on the PR
  before merge, goldens lock it after approval.
