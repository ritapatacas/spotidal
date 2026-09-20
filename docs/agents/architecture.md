# Architecture

Module map for `spotidal/`. Line counts are approximate and only indicate where the
weight sits — use them to judge what is a hub and what is a leaf.

## Controller — `spotidal/controller/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `controller.py` | 693 | `Controller`: session bootstrap (Spotify + TIDAL), the top-level menu loop, `run_doctor()`, `main()`, and the whole `spotidal harvest` CLI (Discogs *and* RYM sources). This is the entry point. |
| `controller_main.py` | 649 | `ControllerMain`: **the real hub.** Download dir, sync/download entry, library monitoring, selection stats, all doctor wrappers, genres, Rekordbox export, every settings mutation. Most feature work lands here. |
| `playlist_controller.py` | 37 | Thin resolver from a playlist reference to a Spotify playlist. |

`Controller.__init__` builds `Model`, opens both sessions, then builds `ControllerMain`
and `PlaylistController` over it. `ControllerMain` receives the `Model` and reaches
everything else through it or by importing model modules directly.

## Model — `spotidal/model/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `library.py` | 968 | `MusicLibrary` — SQLite schema, migrations, file import, playlist/track persistence, reconciliation, genre storage. See [data-model.md](data-model.md). |
| `genre.py` | 788 | Genre/style resolution and tag writing. |
| `doctor.py` | 784 | `Doctor` + `DoctorReport`: the four diagnostics. |
| `discogs.py` | 702 | Discogs API client feeding `genre.py`; the unattended taxonomy harvest. |
| `rym.py` | 550 | **Semi-assisted** Rate Your Music harvest: `RymClient` (Playwright over a real Chrome profile) + `RymTaxonomyFiller`. Never unattended, never blocks on its own. See [workflows.md](workflows.md). |
| `download.py` | 434 | `Download`: by TIDAL id, by URL, by playlist; batching and progress. |
| `auth.py` | 157 | Spotify/TIDAL session open, save, refresh. |
| `settings.py` | 164 | `Settings` + the `DEFAULTS` dict. Single source of truth for settings keys. |
| `rekordbox.py` | 159 | XML + m3u8 export. |
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
| `sync/` | — | `search.py`, `match.py`, `playlists_handler.py`, `request_utils.py`, `cache.py`: the Spotify↔TIDAL matching engine. |
| `type/` | — | `file.py` (the `Files` enum — all user state goes through it), `config.py`, `playlist_ref.py`, `spotify.py`. |

## View — `spotidal/view/`

| Module | ~Lines | Role |
| --- | --- | --- |
| `prompt.py` | 634 | ~22 InquirerPy menu classes. Every menu the user sees is defined here. |
| `menus.py` | 265 | Higher-level menu composition. |
| `view.py` | 189 | Rendering helpers. |
| `text.py` | 105 | `Text` — **all** colored terminal output. |
| `strings.py`, `setup.py`, `sound.py`, `inquirer_keys.py` | small | Literals, first-run credential prompts, notification sound, keybindings. |

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
