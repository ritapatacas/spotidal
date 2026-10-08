# Status

**Snapshot taken 2026-09-07.** This file records what is stale, broken, or in flight.
Re-verify anything here before relying on it — it is the file most likely to drift.

## Do not trust `README.md` as a spec

`README.md` is a user-facing pitch written when the app only synced and downloaded. It
is materially out of date:

- It states credentials live in `~/.config/spotidal/credentials.**yaml**`. The code
  writes **`credentials.yml`** (`Ext.YML` in `spotidal/model/helpers/type/file.py`).
- It documents none of: the SQLite library, the file watcher, the four doctors, Discogs
  genre enrichment, Rekordbox export, FLAC→MP3 conversion, audio normalization, or the
  notification sound.
- It does not mention the `spotidal doctor` CLI subcommand.
- It does not mention the hard external dependencies (`tidal-dl-ng`/`tidekeeper`,
  `ffmpeg`/`ffprobe`).
- Its credits still name `tidal-media-downloader`; the project has since moved to
  `tidal-dl-ng`.

The README was deliberately left unchanged. Use `AGENTS.md` as the source of truth.

## `PLANO_MELHORAMENTO_DATABASE.md` is a plan, partly implemented

That document (Portuguese, 356 lines) is a *design proposal*, explicitly stating it
contains no implementation. Parts of it have since been built, so its description of
the current state is wrong in places:

**No longer true** — it claims `MusicLibrary` lacks upsert and reporting operations.
`upsert_playlist`, `add_playlist_tracks`, `save_playlist_membership`,
`get_playlist_track_stats`, `audit_playlist`, `associate_tidal_playlist` and
`reconcile_location` / `reconcile_all` all exist today. The ffprobe-based MP3 check is
likewise partly built as `run_mp3_quality_doctor`.

**Still open** — these items from the plan remain unaddressed:

- `playlists.name` is still `NOT NULL UNIQUE`, so playlist identity is still the name
  rather than the Spotify/TIDAL id.
- `spotidal/model/helpers/synchronizer.py` still holds no `MusicLibrary` reference;
  persistence still happens in the controller/download layer rather than at the end of
  sync as the plan proposes.
- No `file_validation_results` table exists; the MP3 doctor reports readability but does
  not persist per-file technical/quality status or a validation history.
- `playlist_tracks` still has no `position` column, so playlist order is not stored.

## Known defects (documented, not fixed)

None of these were repaired as part of writing this documentation:

- `spotidal/model/config.py` is a 0-byte file.
- `pyproject.toml` declares dependencies nothing imports (`redis`, `mpegdash`,
  `ratelimit`, `isodate`, `colorama`, `greenlet`, `six`, `pfzy`, `wcwidth`), while the
  binaries the app actually shells out to are declared nowhere.
- `spotidal/controller/playlist_controller.py` has a `__main__` block that constructs
  `PlaylistController()` with no arguments and would fail.
- Loose files sit at the repo root that arguably should not: `.cache.db`,
  `.cache-1138870920`, `credentials.yml`, and a `download/` tree of real audio.

## Fixed on 2026-09-07

Recorded here so the history is not lost:

- `spotidal/view/__init__.py` listed `DefaultSelectionMenu`, `get_string` and
  `format_string` in `__all__` without importing them, so `from spotidal.view import *`
  raised `AttributeError`. `DefaultSelectionMenu` is now imported; `get_string` and
  `format_string` were removed — neither exists anywhere in the codebase.
- `MANIFEST.in` referenced a nonexistent `requirements.txt`; the line was removed.
- `.claude/settings.local.json` allowlisted four commands belonging to the deleted
  `spotidal/web/` layer (two paths under it, two `curl` calls to `127.0.0.1:8888`).
  All four were removed.

## Added on 2026-09-08 — the Rate Your Music harvest

Fases 0–6 of `PLANO_RYM_GENEROS.md` are now implemented except the *review queue* and the
`final_genre` mapping (Fase 5 of the plan, deliberately deferred until the real RYM genre
distribution is visible):

- `spotidal/model/rym.py` (`RymClient` + `RymTaxonomyFiller`): Playwright over a real,
  visible, persistent Chrome profile (`~/.config/spotidal/rym-profile/`), release-level
  dedup, JSON cache, pacing, challenge-pause-for-human, `SiteBlocked`/`BudgetExhausted`.
- Schema in `library.py`: `rym_release`, `rym_release_genre`, and `harvest_log` rebuilt
  with PK `(track_id, source)`, back-filling existing Discogs rows with `source='discogs'`.
- CLI: `spotidal harvest rym [selection|all|<playlist>] [--retry-unmatched]
  [--max-pages N]`. `harvest` without a source keeps meaning Discogs — existing
  cron/launchd jobs are untouched. Exit codes: `0` done, `2` blocked/unresolved
  challenge, `3` page budget exhausted.
- Menu: Utils → genres → "fill genres from rate your music (browser)" (scope submenu:
  selected / all / select playlists).
- Settings: `rymMinDelay` (10), `rymMaxDelay` (25), `rymMaxPages` (80) in `DEFAULTS`.
- `pyproject.toml` gained `playwright`; the browser itself is a hard requirement
  (see `AGENTS.md`): `poetry run playwright install chrome`.

Still open (planned, not built): the manual review queue for low-confidence RYM matches,
and the vocabulary mapping from RYM labels into `final_genre`/`track_genre_style`.

## `spotidal/web/` — deleted, not dormant

The directory contains only `__pycache__` (`server`, `state`, `spotify_folders`,
`api/auth`, `api/playlists`, `api/sync`). `git ls-files spotidal/web` returns nothing
and there is no history for it: a local web/API layer existed on this machine and was
never committed. Do not attempt to reconstruct it from the bytecode. If a web layer is
wanted again, it should be written fresh.

**Do not confuse this with `spotidal/webui/`** (added 2026-09-20), which is a live,
wired-in, unrelated module — the `search` menu's local track browser / DJ mix-suggestion
UI. See [architecture.md](architecture.md#web-ui--spotidalwebui).

## Uncommitted work in flight

`spotidal/webui/` (`server.py`, `page.py`, `__init__.py`) — untracked as of 2026-09-20
— is now committed.

As of 2026-09-25, the working tree has real uncommitted changes across
`controller.py`, `controller_main.py`, `doctor.py`, `download.py`,
`helpers/sync/search.py`, `library.py`, `rekordbox.py`, `view/prompt.py`,
`view/view.py`, `webui/page.py`, `webui/server.py`, plus a new
`docs/rekordbox-import.md` — see "Added/changed on 2026-09-25" below for what they
are. Check `git status` before assuming the committed history reflects what is on
disk.

## Added/changed on 2026-09-25 — utils reorg, rekordbox export, playlist-consistency review

Not yet committed (see above). In rough order:

- **Rekordbox export** (`rekordbox.py`, `controller_main.py`, `controller.py`):
  `export to rekordbox` moved to the main menu (it is no longer under `utils` at
  all — `UtilsMenu.EXPORT_REKORDBOX` became dead code across the reorg below and was
  removed), now scoped
  to a playlist selection (checkbox list, not "every playlist") via a new `names`
  param on `RekordboxExport.export_xml`/`export_m3u8`, and backs up any existing
  `rekordbox.xml` to a timestamped `.bak-YYYYMMDD-HHMMSS` copy before overwriting.
  New doc: [`docs/rekordbox-import.md`](../rekordbox-import.md) (user-facing, not
  agent orientation — steps + tips for the actual rekordbox-side import).
- **`utils` menu reorganized** around "composite routines at the top level, narrow
  commands in submenus": `sync database` (new — chains reconcile → playlist refresh →
  repair), `manage selected playlist`, `playlists doctors` (with `sync playlists
  (audit + refresh)`, folding in what used to be a separate "watch playlist files"
  step for the common case — see architecture.md), `genres`, `doctors` (nesting
  `download doctors`, `database doctors`, `local files doctors`). Labels were also
  reworded to say explicitly which two things they compare (`tidal vs local` /
  `spotify vs local` / `disk vs db`) — see architecture.md's "Don't conflate these
  three" table in workflows.md for why that distinction matters.
- **`download doctor`** now runs a `tmp cleanup` step first (same as the standalone
  `clean tmp files` action).
- **`by_td_ids()` download loop** (`download.py`) only visits playlists with pending
  tracks in its per-playlist progress loop, instead of walking every selected
  playlist even when 0 are pending.
- **`audit_playlist_consistency`** (`controller_main.py`) rewritten: four-way
  classification (flagged title/artist / album differs / tidal_id differs / not
  found) instead of one mixed "flagged" bucket; ISRC-only local lookup replaced with
  an ISRC-then-title/artist fallback (`MusicLibrary.find_tracks_by_title_like`,
  length-ordered); results persisted to CSV under `~/.config/spotidal/logs/` (DB for
  the flagged bucket). See workflows.md section 3 for the full breakdown and the
  "don't conflate" table.
- **New `/review` page** in the local search UI (`webui/page.py`, `webui/server.py`):
  interactive queue for the audit's four buckets (three have tabs), with a TIDAL
  search-and-fix panel for the flagged bucket. `run_server()` now takes an optional
  `td_session` for this.
- **Sync performance fix** (`helpers/sync/search.py`): the MusicBrainz
  original-album lookup — rate-limited to ~1 req/s process-wide — now only runs
  after a TIDAL match is found, not unconditionally per track; this was making a
  first-time sync of a large playlist (~1400 tracks) look frozen for many minutes.
  Per-track `found:`/`not found:` logging added to `search_new_tracks_on_td()`.

## No test suite

There is no `tests/` directory, no `test_*.py`, no pytest configuration, and no CI
(`.github/` does not exist). The acceptance-test lists inside
`PLANO_MELHORAMENTO_DATABASE.md` have no corresponding code. See the verification
section of `AGENTS.md` for what to do instead.
