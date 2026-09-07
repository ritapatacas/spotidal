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

- `spotidal/view/__init__.py` lists `DefaultSelectionMenu`, `get_string` and
  `format_string` in `__all__` without importing them — a star-import from that package
  raises `AttributeError`.
- `spotidal/model/config.py` is a 0-byte file.
- `MANIFEST.in` references `requirements.txt`, which does not exist, so the sdist
  manifest is broken.
- `.claude/settings.local.json` allowlists `spotidal/web/api/playlists.py` and
  `spotidal/web/static/app.js` — neither exists.
- `pyproject.toml` declares dependencies nothing imports (`redis`, `mpegdash`,
  `ratelimit`, `isodate`, `colorama`, `greenlet`, `six`, `pfzy`, `wcwidth`), while the
  binaries the app actually shells out to are declared nowhere.
- `spotidal/controller/playlist_controller.py` has a `__main__` block that constructs
  `PlaylistController()` with no arguments and would fail.
- Loose files sit at the repo root that arguably should not: `.cache.db`,
  `.cache-1138870920`, `credentials.yml`, and a `download/` tree of real audio.

## `spotidal/web/` — deleted, not dormant

The directory contains only `__pycache__` (`server`, `state`, `spotify_folders`,
`api/auth`, `api/playlists`, `api/sync`). `git ls-files spotidal/web` returns nothing
and there is no history for it: a local web/API layer existed on this machine and was
never committed. Do not attempt to reconstruct it from the bytecode. If a web layer is
wanted again, it should be written fresh.

## Uncommitted work in flight

At the time of writing the tree carries roughly 2.3k uncommitted lines. Untracked:
`spotidal/model/discogs.py`, `doctor.py`, `genre.py`, `rekordbox.py`, and
`spotidal/view/sound.py`. Modified: `controller.py`, `controller_main.py`,
`download.py`, `flac_to_mp3.py`, `helpers/td_downloader.py`, `library.py`,
`settings.py`, `view/prompt.py`, `view/view.py`.

Check `git status` before assuming the committed history reflects what is on disk.

## No test suite

There is no `tests/` directory, no `test_*.py`, no pytest configuration, and no CI
(`.github/` does not exist). The acceptance-test lists inside
`PLANO_MELHORAMENTO_DATABASE.md` have no corresponding code. See the verification
section of `AGENTS.md` for what to do instead.
