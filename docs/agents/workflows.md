# Workflows

The four flows most feature work touches, traced end to end.

## 1. Sync (Spotify → TIDAL)

```
MainMenu "sync"                       spotidal/view/prompt.py
  → Controller.run loop               spotidal/controller/controller.py
  → ControllerMain.sync(e)            spotidal/controller/controller_main.py
  → sync_playlists_wrapper()          spotidal/model/helpers/synchronizer.py
  → helpers/sync/search.py, match.py, playlists_handler.py
  → TIDAL playlist updated
```

`ControllerMain.sync_url()` is the same flow entered from a pasted URL;
`_start_playlist_job()` wraps a single playlist reference.

**Important asymmetry:** `synchronizer.py` contains *no* `MusicLibrary` reference. It
updates the playlist on TIDAL and returns; database persistence happens afterwards in
the controller and download layers. So a change in matching behaviour will not show up
in the database unless the caller also persists it. Tracks that fail to match TIDAL are
the ones most likely to be lost — they have no TIDAL id to persist by.

**MusicBrainz cost.** `td_search()` (`helpers/sync/search.py`) asks MusicBrainz whether
a track's Spotify-reported album is a compilation/reissue of a genuine original studio
album — but only *after* a TIDAL match is already found (`spotify_result`), not
unconditionally. MusicBrainz's public API is rate-limited to ~1 req/s **process-wide**
(a single `threading.Lock` in `helpers/sync/musicbrainz.py`, shared across every
concurrent search task regardless of `max_concurrency`), so calling it for every track
serializes a first-time sync of a large playlist to many minutes of near-zero visible
progress — this happened in practice on a ~1400-track playlist. Don't move this call
back above the TIDAL search without re-checking that math. `search_new_tracks_on_td()`
logs one `found: <title> — <artist> -> ...` / `not found: <title> — <artist>` line per
track via `tqdm.write` as each completes.

## 2. Download

```
MainMenu "download" → ControllerMain.download(e) / download_url(url)
  → Download (spotidal/model/download.py)
      _prepare_tracks()   → MusicLibrary.available_track_ids()   # skip what exists
      by_td_id / by_td_ids / by_url / _download_tidal_playlist()
        → td_downloader.py → external `tidal-dl-ng` / `tidekeeper` subprocess
      MusicLibrary.associate_tidal_playlist(...)                 # persist membership
      _reconcile_downloaded_files() → MusicLibrary.reconcile_all()
```

Notes:

- Downloads are batched (`batchSize`, `parallelBatches` in settings) with a `tqdm`
  subclass, `DownloadProgress`, for per-track percentage.
- `by_td_ids()` fetches/prepares every selected playlist first (unavoidable — that's
  how it learns what's pending), but its per-playlist progress loop only visits
  playlists that actually have pending tracks; a playlist with 0 to download no
  longer gets a header line and a wasted "playlist N/M" step.
- A stale TIDAL session surfaces as `TidalSessionStaleError` from `td_downloader`; the
  controller catches it and routes to `Model.refresh_td_session()`, which refreshes the
  token or falls back to an interactive tidekeeper login.
- Tracks that are not found are appended to `Files.NOT_FOUND` (`not_found.yml`).
- If `autoConvertMp3` is on, `flac_to_mp3.py` runs after the download.

## 3. Doctors (diagnostics)

`spotidal/model/doctor.py` defines `Doctor` with four runs, each wrapped by a
`ControllerMain.doctor_*` method and reachable both from the Utils menu and from the
CLI (`Controller.run_doctor` maps the scope string to the wrapper):

| Scope | Method | What it checks |
| --- | --- | --- |
| — | `run_download_doctor` | The full download pipeline: settings, binary, login, a probe download. |
| `playlists` | `run_playlists_doctor` | The saved selection against the database. |
| `missing` | `run_missing_tracks_doctor` | Tracks with no local file; can download them (`confirm=True` by default) and offers a manual TIDAL search for unmatched ones. |
| `mp3` | `run_mp3_quality_doctor` | Runs `ffprobe` over MP3s and compares against the FLAC source. |
| `all` | `run_all` | All of the above. |

Output goes through `DoctorReport` (`.ok/.info/.warn/.fail/.step/.finish`), which
accumulates results and decides the process exit code. Add new checks as
`DoctorReport` calls — do not `print` from inside a doctor.

`_ffprobe_stream_info()` is the shared ffprobe wrapper: it uses `subprocess` with
separate arguments, a timeout, and JSON output. Reuse it rather than parsing ffprobe
text.

`run_download_doctor` also runs a `tmp cleanup` step first (the same
`clean_tmp()` + `purge_temp_artifacts()` as the standalone `clean tmp files` menu
item), before the tidekeeper/token/db/test-download checks — added so the one-click
"is the pipeline healthy" doctor doesn't need a separate manual cleanup pass first.

`utils > doctors > playlists doctors` wraps `run_playlists_doctor` in
`Controller._playlists_doctor()` (`controller.py`): after the read-only DB audit, if
the saved default selection is non-empty it offers to refresh those playlists from
TIDAL right there (`ControllerMain.get_selection_stats(force_refresh=True)`) — audit
and fix in one action, folding in what used to be the separate "watch playlist files"
step for this common case. `watch playlist files` still exists standalone
(`utils > doctors > database doctors`) for an ad-hoc selection not tied to the saved
default.

### Don't conflate these three "is my library complete" checks

They compare different pairs of things and give very different numbers for the same
playlist — this caused real confusion in practice (0 missing from one, hundreds "not
found" from another, on the same playlist, same session):

| Check | Compares | Blind to |
| --- | --- | --- |
| `run_missing_tracks_doctor` (`missing tracks doctor`) | **TIDAL playlist mirror** vs local files | Spotify tracks never matched into the TIDAL mirror at all — they're not "missing", they're just never seen |
| `get_selection_stats` (the `tracks/local/missing` table — `view selection`, `refresh selection stats`, and printed after most doctor/refresh actions) | Same as above: **TIDAL playlist** (`total`) vs local files matched (`local`) | Same blind spot — `total` is never the Spotify track count |
| `audit_playlist_consistency` (`audit playlist consistency`) | The **live Spotify playlist** vs the local DB, matched primarily by ISRC with a title+artist fallback | Nothing upstream — this is the only one of the three that ever asks Spotify directly |

A `sync` that gets interrupted (or that fails to match a track at all — see the
MusicBrainz note above) leaves the TIDAL mirror short of the Spotify playlist. The
first two checks won't notice; only `audit_playlist_consistency`'s "not found" bucket
will. If `missing_tracks_doctor` says 0 missing but the audit says otherwise, re-sync
the playlist (not "download missing" — that only ever acts on what's already in the
TIDAL mirror) and check again.

### The playlist-consistency audit's output

`ControllerMain.audit_playlist_consistency(names)` fetches each playlist fresh from
Spotify and classifies every track into exactly one bucket:

1. **Flagged** — title or artist differs from the local DB row. The audit's actual
   review target. Written to `tracks.review_reason` (`MusicLibrary.set_review`);
   cleared automatically on a later run if the track no longer qualifies.
2. **Album differs** — title and artist match, only the album diverges. Deliberately
   *not* flagged: Spotify often files a track under a "best of"/compilation while the
   library keeps the real original album (the same divergence `prefer_original_album`
   already handles at download time), so this is expected and not a review target.
   Written to `~/.config/spotidal/logs/album_diff_review.csv`.
3. **tidal_id differs** — everything else matches but the TIDAL id an exact-ISRC
   search finds disagrees with the stored one. Written to
   `~/.config/spotidal/logs/tidal_diff_review.csv`. No dedicated review tab yet.
4. **Not found** — no local match at all, by ISRC *or* by a normalized title+artist
   fallback (`MusicLibrary.find_tracks_by_title_like`, ordered by title length so a
   short/common fragment surfaces its exact-length match first — without that
   ordering, a `LIMIT`-capped candidate set can silently miss the real match).
   Written to `~/.config/spotidal/logs/not_found_review.csv`.

ISRC alone is unreliable as the primary lookup key: TIDAL and Spotify frequently carry
different regional/release ISRCs for the same recording — `tracks.isrc` is whatever
the downloaded file's own tag says (from TIDAL), not Spotify's. This is exactly why
`helpers/sync/match.py` never trusts ISRC alone either; the audit's title+artist
fallback exists for the same reason. Review these results at `utils > doctors >
playlists doctors > audit playlist consistency`'s output, or interactively at
`/review` in the local search UI (see below).

## 4. Watcher and reconciliation

Two paths keep the database in step with the filesystem:

- **Live**: `library_watcher.py` runs a watchdog observer, started/stopped through
  `ControllerMain` (`stop_library_monitoring()` is called on every exit path, including
  `KeyboardInterrupt` — preserve that if you touch shutdown).
- **Batch**: `ControllerMain.reconcile_library()` → `MusicLibrary.reconcile_all()`,
  which walks each location, calls `import_file()` for new files, and calls
  `mark_missing()` for paths that vanished.

Reconciliation is non-destructive: a vanished file gets `missing_at` set, not deleted.
`purge_*` methods are the only ones that remove rows, and they are invoked explicitly.

Both are gated by the `watcherEnabled` / `databaseEnabled` settings; check them before
assuming the database is being updated.

## 5. Genre fill and the Discogs harvest

Two consumers share one Discogs client (`DiscogsClient`, `spotidal/model/genre.py`):

- **`GenreFiller`** (`genre.py`) — interactive. Writes `tracks.genre`/`style` *and* the
  genre tag inside each audio file, then offers a manual review pass.
- **`DiscogsTaxonomyFiller`** (`discogs.py`) — the unattended harvest. Writes **only** the
  `discogs_*` tables; never `tracks.genre`, never file tags.

### The unattended harvest

```
poetry run spotidal harvest [selection|all|<playlist>] [--retry-unmatched] [--max-calls N]
  → ControllerMain.harvest_discogs()
  → DiscogsTaxonomyFiller.harvest(rows)
      resolve()          # album search, then ISRC as fallback
      release_detail()
      store()            # discogs_release + discogs_release_genre_style
```

Exit codes: `0` finished, `2` the API gave up, `3` call budget exhausted — so `cron`/`launchd`
can tell what happened.

`resolve()` searches by album (retried through `clean_query()` variants and the track title),
accepting an exact normalized title or a token-subset of it, and only then falls back to
ISRC→MusicBrainz→Discogs. **The order matters**: the album search answers ~89% of this library
on its own, while the ISRC route resolved ~10% and costs a 1.1s MusicBrainz call on every
track — roughly an hour a night spent on misses if it runs first.

Discogs coverage is uneven, and knowing where it fails saves re-litigating it: catalogue music
resolves well, contemporary digital-only singles and EPs are largely absent from Discogs
entirely. Those tracks belong in the manual review pass. Genre by artist consensus was measured
(16/23 on one electronic playlist) and **deliberately rejected** — it is a guess about the
artist, not a fact about the release.

### Resuming and not repeating work

Three mechanisms, all in the database or the on-disk cache:

- `_bound_track_ids()` — tracks already carrying a selected release are skipped.
- `harvest_log` — a track that resolves to nothing records `outcome='unmatched'` and an attempt
  count; after `MAX_UNMATCHED_ATTEMPTS` it is skipped unless `--retry-unmatched`. API failures
  deliberately do **not** increment it, or one bad night would burn the attempts of perfectly
  resolvable tracks.
- The JSON cache stores search hits *and* misses, checkpointed every `CHECKPOINT_EVERY` calls
  rather than once at the end.

### When the API misbehaves

`DiscogsClient` distinguishes "this record does not exist" from "this service is unwell". A 404
or an empty result set is an answer and closes the breaker; a 429/503/5xx/timeout trips it,
pausing that host for 1, 2, 4, 8, 16 minutes (capped at 30). After `BREAKER_GIVE_UP_AFTER`
pauses with no success it raises `ApiUnavailable` so the run stops and checkpoints instead of
hammering all night. `BudgetExhausted` does the same for `--max-calls`.

`bucket_for()` folds Discogs' ~757 styles into DJ-usable buckets, checking the exact style
table, then `SUBSTRING_RULES` in order, then the genre table. **Rule order matters** — a more
specific rule must precede a broader one that would also match (`"pop rock"` before `"pop"`),
or the same artist lands in different buckets depending on which style Discogs lists first.

### The semi-assisted RYM harvest

Rate Your Music has no API and answers automation with agressive "I'm not a robot"
interstitials, so this harvest is the opposite of the Discogs one: it runs in a **real,
visible Chrome window** and counts on a human nearby. Everything in the design exists to
minimise the number of page loads (the only metric that matters against an anti-bot
system): resolve one page per **release**, not per track.

```
poetry run spotidal harvest rym [selection|all|<playlist>] [--retry-unmatched] [--max-pages N]
  → RymTaxonomyFiller.harvest(rows)                    spotidal/model/rym.py
      _release_groups()        # one (artist, album) group, fan-out to its tracks
      resolve() + search_release()   # /search?searchterm=...&searchtype=l
      release_detail()         # primary/secondary genres + descriptors
      store()                  # rym_release + rym_release_genre only
```

The Utils → genres → "fill genres from rate your music (browser)" menu path launches the
same code with the settings-pace (`rymMinDelay`/`rymMaxDelay`/`rymMaxPages`); from the
menu there is no `--max-pages` override.

Key behaviours:

- **Persistent profile.** Playwright launches Chrome with `channel="chrome"`,
  `headless=False`, `user-data-dir=~/.config/spotidal/rym-profile/`. Cookies
  (Cloudflare, RYM session) survive between runs, so reputation accumulates. The first
  run is the moment to log in to RYM by hand. The launch passes `chromium_sandbox=True`:
  Playwright 1.55+ adds `--no-sandbox` by default, but that is a Linux-only flag that
  real Chrome on macOS does not understand and answers with a warning banner.
- **Pacing**: `rymMinDelay`–`rymMaxDelay` seconds between pages (default 10–25), a long
  pause of 60–120 s every 20 pages, zero concurrency, a `--max-pages` session budget.
- **Challenge = pause for a human, never a bypass.** On detecting the interstitial the
  harvest rings the notification sound and polls every ~5 s for up to 10 min while the
  user resolves it in the visible window. After 3 challenges in one session it raises
  `SiteBlocked` and checkpoints. RYM sometimes answers with a test that *renews in
  place* — every checkbox solve leads to the next test because the session has been
  flagged (fresh anonymous profile, request burst). A renewal is detected by comparing
  the interstitial's footprint between polls and burns one challenge slot, so a
  flagged session aborts after ~3 renewals instead of looping for 10 min. The
  detection markers in `rym.py` are Cloudflare's generic ones — the RYM interstitial
  was never hit during the spike, so readjust the first time a real challenge is seen.
- **Same bookkeeping as Discogs**, with `harvest_log.source='rym'`: `MAX_UNMATCHED_ATTEMPTS`,
  `--retry-unmatched`, and site failures that never increment the attempt counter.
- **JSON cache** (`~/.config/spotidal/rym_cache.json`) stores hits *and* misses forever,
  checkpointed every 20 calls.

Exit codes match the Discogs harvest: `0` finished, `2` the site blocked the run or a
challenge went unresolved, `3` the page budget was exhausted. `harvest` with no source
token still means the unattended Discogs harvest, so existing cron/launchd jobs are
unchanged.

## 6. The local search UI

```
MainMenu "search"                          spotidal/view/prompt.py
  → Controller.run loop                    spotidal/controller/controller.py
  → ControllerMain.run_search_ui()         spotidal/controller/controller_main.py
  → run_server(library, td_session=...)    spotidal/webui/server.py
      ThreadingHTTPServer on 127.0.0.1:8383, opens the browser, blocks until Ctrl+C
      GET /            → page.py PAGE_HTML           track browser
      GET /suggest     → page.py SUGGEST_PAGE_HTML    per-track mix suggestions
      GET /review      → page.py REVIEW_PAGE_HTML     playlist-consistency review queue
      GET /api/*       → MusicLibrary.search_filter_options / playlist_tree /
                          genre_counts / search_tracks / suggest_tracks / camelot_related
      GET/POST /api/review/*  → the review queue's own API, see below
```

Open `/review` from the main page's Start menu ("Review Audit"). It reads what
`audit_playlist_consistency` produced (see section 3 above for the four buckets):
**Flagged** is DB-backed (`MusicLibrary.flagged_tracks()` / `set_review()`) and its
tab lets you dismiss a flag or search TIDAL and pick a fix
(`POST /api/review/fix` → `MusicLibrary.set_tidal_id()`, which also clears the flag).
**Album differs** and **Not found** are CSV-backed
(`~/.config/spotidal/logs/{album_diff,not_found}_review.csv`), read and dismissed
generically through `REVIEW_CSV_BUCKETS` in `server.py`
(`GET /api/review/<bucket>`, `POST /api/review/dismiss/<bucket>`) — add a bucket there
(and a tab in `page.py`, following the existing two as a template) rather than
one-off endpoints if another CSV-backed review category shows up. The `tidal-diff`
bucket exists in `REVIEW_CSV_BUCKETS` and gets written by the audit, but has no tab
yet — reachable via its endpoint or the raw CSV.

Requires `databaseEnabled` and a resolvable local directory — same guard as every other
`ControllerMain` method touching `self._library`; see `run_search_ui()`'s early returns.
There is no auth and no CORS handling because the server only ever binds loopback; do
not change `host` without treating that as a security-relevant change.

`suggest_tracks()` (`library.py`) ranks candidates by Camelot-wheel key compatibility,
BPM closeness (within a tolerance fraction of the seed BPM), and shared genre/style —
mirroring how a DJ would judge a mix by ear, not a generic "similar tracks" measure.
BPM/key come from `RekordboxImport` (`rekordbox.py`), so this view is only useful for
tracks Rekordbox has already analyzed.
