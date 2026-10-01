# Architecture

Module map for `spotidal/`. Line counts are approximate and only indicate where the
weight sits — use them to judge what is a hub and what is a leaf.

## Controller — `spotidal/controller/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `controller.py` | 762 | `Controller`: session bootstrap (Spotify + TIDAL), the top-level menu loop, `run_doctor()`, `main()`, and the whole `spotidal harvest` CLI (Discogs *and* RYM sources). This is the entry point. Also holds the `utils` submenu wiring — see the `utils` layout below. |
| `controller_main.py` | 917 | `ControllerMain`: **the real hub.** Download dir, sync/download entry, library monitoring, selection stats, all doctor wrappers, genres, Rekordbox export, playlist-consistency audit, every settings mutation. Most feature work lands here. |
| `playlist_controller.py` | 37 | Thin resolver from a playlist reference to a Spotify playlist. |

### The `utils` menu layout

`utils` (`controller.py`) is organized around one rule: composite/routine actions
that "do several things" live at the top level; narrow, single-purpose commands are
tucked into submenus. Current top level: `sync database`, `manage selected
playlist`, `playlists`, `genres`, `doctors`. `doctors` nests the three domain doctor
submenus (`playlists doctors`, `download doctors`, `database doctors` →
`local files doctors`). `export to rekordbox` lives on the *main* menu, not under
`utils`, alongside `download`/`sync`/`explore library`.

Menu labels are deliberately explicit about which two things they compare —
`tidal vs local`, `spotify vs local`, `disk vs db` — because several checks look
similar but aren't: `missing tracks doctor` / `get_selection_stats` (the
`tracks/local/missing` table) only ever compare the **TIDAL playlist mirror**
against local files, and are blind to Spotify tracks that were never matched into
that TIDAL mirror in the first place. Only `audit playlist consistency` reads the
**Spotify** playlist directly. Don't conflate the two when diagnosing "why does the
count look wrong" — see [workflows.md](workflows.md) for the full breakdown.

`Controller.__init__` builds `Model`, opens both sessions, then builds `ControllerMain`
and `PlaylistController` over it. `ControllerMain` receives the `Model` and reaches
everything else through it or by importing model modules directly.

## Model — `spotidal/model/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `library.py` | 1372 | `MusicLibrary` — SQLite schema, migrations, file import, playlist/track persistence, reconciliation, genre storage, plus the review-queue reads (`flagged_tracks`, `find_tracks_by_title_like`, `set_review`) backing `/review`. See [data-model.md](data-model.md). |
| `genre.py` | 788 | Genre/style resolution and tag writing. |
| `doctor.py` | 784 | `Doctor` + `DoctorReport`: the diagnostics reachable under `utils > doctors`, plus `run_download_doctor`'s tmp-cleanup step. |
| `discogs.py` | 702 | Discogs API client feeding `genre.py`; the unattended taxonomy harvest. |
| `rym.py` | 550 | **Semi-assisted** Rate Your Music harvest: `RymClient` (Playwright over a real Chrome profile) + `RymTaxonomyFiller`. Never unattended, never blocks on its own. See [workflows.md](workflows.md). |
| `download.py` | 434 | `Download`: by TIDAL id, by URL, by playlist; batching and progress. Only iterates playlists that actually have pending tracks — see [workflows.md](workflows.md). |
| `auth.py` | 157 | Spotify/TIDAL session open, save, refresh. |
| `settings.py` | 164 | `Settings` + the `DEFAULTS` dict. Single source of truth for settings keys. |
| `rekordbox.py` | 273 | `RekordboxImport` (BPM/key from rekordbox's own DB) + `RekordboxExport` (XML + m3u8), scoped to a playlist-name selection, with an automatic timestamped backup of any existing `rekordbox.xml`. |
| `model.py` | 106 | `Model` facade: sessions, playlist listing, saved selection. Deliberately thin. |
| `library_watcher.py` | 100 | watchdog observer that keeps the DB in step with the filesystem. |
| `normalize_audio.py`, `flac_to_mp3.py` | 94 / 144 | ffmpeg wrappers. |
| `sync.py` | 33 | Thin `Sync` wrapper over the helpers below. |
| `config.py` | 0 | **Empty. Dead.** Do not import. |

### `spotidal/model/helpers/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `td_downloader.py` | 638 | Wraps the external `tidal-dl-ng` / `tidekeeper` binary: settings generation, login, token refresh, invocation. Raises `TidalSessionStaleError`. |
| `synchronizer.py` | 132 | `sync_playlists_wrapper` / `sync_favorites_wrapper`. **Holds no `MusicLibrary` reference** — see [workflows.md](workflows.md). |
| `tidalapi.py`, `cache.py`, `utils.py` | small | TIDAL helpers, request cache, parsing. |
| `sync/` | — | `search.py`, `match.py`, `musicbrainz.py`, `playlists_handler.py`, `request_utils.py`, `cache.py`: the Spotify↔TIDAL matching engine. `td_search()` in `search.py` only calls MusicBrainz's `original_album_name()` (rate-limited to ~1 req/s process-wide, via a global lock in `musicbrainz.py`) *after* a TIDAL match is already found — calling it unconditionally per track serialized a bulk sync of hundreds of new tracks to many minutes of near-zero visible progress. `search_new_tracks_on_td()` logs a `found:`/`not found:` line per track via `tqdm.write`. |
| `type/` | — | `file.py` (the `Files` enum — all user state goes through it), `config.py`, `playlist_ref.py`, `spotify.py`. |

## View — `spotidal/view/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `prompt.py` | 634 | ~22 InquirerPy menu classes. Every menu the user sees is defined here. |
| `menus.py` | 265 | Higher-level menu composition. |
| `view.py` | 189 | Rendering helpers. |
| `text.py` | 105 | `Text` — **all** colored terminal output. |
| `strings.py`, `setup.py`, `sound.py`, `inquirer_keys.py` | small | Literals, first-run credential prompts, notification sound, keybindings. |

## Web UI — `spotidal/webui/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `server.py` | 219 | `run_server(library, td_session=None, ...)`: a stdlib `ThreadingHTTPServer`, loopback by default (`127.0.0.1:8383`). Serves the pages and a JSON API over `MusicLibrary` (`/api/options`, `/api/playlist-tree`, `/api/genre-counts`, `/api/tracks`, `/api/suggest`, `/api/camelot`), plus the review API described below. `td_session` is optional and only needed for the review page's "search TIDAL" panel. |
| `page.py` | 1385 | Single-file HTML/CSS/JS (retro Windows-95-styled) for three views: `/` a filterable track browser, `/suggest` a per-track DJ mix-suggestion popup, `/review` the playlist-consistency review queue (below). No build step, no framework — each is a literal string served as-is. |

Entry point: `ControllerMain.run_search_ui()` (`controller_main.py`) → `MainMenu.SEARCH`
in the top-level menu (`controller.py`), which now also passes the live TIDAL session
through. Requires the local database (`databaseEnabled` setting) and blocks the
terminal until Ctrl+C, same as any other menu action — it does not run in the
background. Opens the user's browser automatically unless `open_browser=False`.

### `/review` — the playlist-consistency review queue

Opened from the main page's Start menu ("Review Audit"). Reads what
`ControllerMain.audit_playlist_consistency()` produces (see
[workflows.md](workflows.md) for the audit itself):

- **Flagged** tab — DB-backed (`tracks.review_reason`, via `MusicLibrary.flagged_tracks()`
  / `set_review()`); title/artist mismatches only. Per row: dismiss (clears the
  flag), or search TIDAL and pick a candidate to correct `tracks.tidal_id`
  (`POST /api/review/fix`, `MusicLibrary.set_tidal_id()`).
- **Album differs** / **Not found** tabs — CSV-backed
  (`~/.config/spotidal/logs/{album_diff,not_found}_review.csv`), read/dismissed
  generically through `REVIEW_CSV_BUCKETS` in `server.py`
  (`GET /api/review/<bucket>`, `POST /api/review/dismiss/<bucket>`). A third bucket,
  `tidal-diff`, is written but has no dedicated tab yet — check its CSV directly if
  needed.

## External boundaries

Four processes/services sit outside the code and are the usual source of failure:

1. **Spotify Web API** via `spotipy` — token cached on disk.
2. **TIDAL API** via `tidalapi` — token refresh in `Model.refresh_td_session()`, which
   falls back to an interactive `tidekeeper` login.
3. **`tidal-dl-ng` / `tidekeeper` subprocess** — the actual downloader.
4. **`ffmpeg` / `ffprobe` subprocesses** — conversion, normalization, MP3 inspection.
5. **Google Chrome via Playwright** (`spotidal/model/rym.py`) — a real, visible
   browser with a persistent profile under `~/.config/spotidal/rym-profile/`. RYM has
   no API and blocks plain HTTP clients, so every request is a real page load. The
   `playwright` package is declared in `pyproject.toml`; the browser binary is not
   (`poetry run playwright install chrome`).

Boundaries 1–4 are fully unattended after authentication; boundary 5 deliberately is
not — a human keeps the window visible and resolves the occasional "I'm not a robot"
challenge (see [workflows.md](workflows.md)).
