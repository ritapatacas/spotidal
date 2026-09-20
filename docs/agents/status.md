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

As of 2026-09-20, `spotidal/webui/` (`server.py`, `page.py`, `__init__.py`) is untracked
despite being fully wired in — `controller_main.py` imports and calls it, and the
`search` menu entry reaches it. It works (`poetry run python -m compileall` and manual
launch both succeed); it's simply never been committed. `library.py`'s
`search_filter_options`/`playlist_tree`/`genre_counts`/`search_tracks`/`suggest_tracks`
and the `bpm`/`musical_key` columns it depends on **are** committed, from the RYM
harvest batch — so the DB side of this feature predates and outlives its own UI's
commit status.

Check `git status` before assuming the committed history reflects what is on disk.

## No test suite

There is no `tests/` directory, no `test_*.py`, no pytest configuration, and no CI
(`.github/` does not exist). The acceptance-test lists inside
`PLANO_MELHORAMENTO_DATABASE.md` have no corresponding code. See the verification
section of `AGENTS.md` for what to do instead.
