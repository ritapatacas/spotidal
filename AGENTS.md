# AGENTS.md

Orientation for AI agents working in this repository. Read this first, then open
the file under `docs/agents/` that matches your task.

## What this project is

Spotidal is a **local, single-user, interactive terminal application** (Python 3.11+,
Poetry) that:

- reads playlists from **Spotify** (via `spotipy`),
- matches and syncs them to **TIDAL** (via `tidalapi`),
- downloads the matched tracks by shelling out to an external TIDAL downloader,
- indexes the resulting local audio files in a **SQLite music library**,
- and runs "doctor" diagnostics over that library (missing tracks, MP3 quality, …).

It is not a service and exposes no external API. The primary UI is InquirerPy
prompts; the `search` menu item is the one exception — it launches a local,
loopback-only web UI (`spotidal/webui/`) for browsing/searching the library and
getting DJ mix suggestions. See [architecture.md](docs/agents/architecture.md).

## Running it

```bash
poetry install
poetry run spotidal                    # interactive menu
poetry run spotidal doctor             # same as `doctor all`
poetry run spotidal doctor playlists   # also: missing | mp3 | all
```

The console script is declared in `pyproject.toml` and resolves to
`main()` in `spotidal/controller/controller.py`.

## Layout

Loose MVC, with the dependency direction `controller → model` and `controller → view`:

| Path | Role |
| --- | --- |
| `spotidal/controller/` | Orchestration. `ControllerMain` holds most application logic. |
| `spotidal/model/` | Data, persistence, and all external services (Spotify, TIDAL, Discogs, ffmpeg). |
| `spotidal/view/` | Terminal only — InquirerPy menus and colored output. Holds no logic. |
| `spotidal/webui/` | Local search UI: a stdlib `http.server` (`server.py`) serving a single-file HTML/JS page (`page.py`) against `MusicLibrary`. Only path with an HTTP surface, and it's loopback-only, launched on demand from the `search` menu. |

`view` must never import from `model`. Menus return plain strings; the controller
decides what they mean.

## Hard requirements not declared in `pyproject.toml`

These are real runtime dependencies that Poetry will not install for you:

- **`tidal-dl-ng` / `tidekeeper`** — the actual downloader, invoked as a subprocess
  and partly imported (`spotidal/model/helpers/td_downloader.py`). Downloads fail
  without it.
- **`ffmpeg` / `ffprobe`** — used for MP3 conversion, audio normalization, and the
  MP3 quality doctor (`spotidal/model/doctor.py`, `flac_to_mp3.py`, `normalize_audio.py`).
- **Google Chrome via Playwright** — used by the Rate Your Music harvest
  (`spotidal/model/rym.py`). The `playwright` package *is* declared in
  `pyproject.toml`, but the browser binary is installed separately with
  `poetry run playwright install chrome`, and the harvest runs in a real,
  visible Chrome window with a persistent profile under
  `~/.config/spotidal/rym-profile/` (challenges solved by hand; see
  `docs/agents/workflows.md`).

If you add a feature that depends on another external binary, document it here.

## Where state lives

All user state is under `~/.config/spotidal/`: `settings.json`,
`default_settings.json`, `playlists.json`, `parsed_playlists.yml`,
`selection.json`, `not_found.yml`, `credentials.yml`.

Always go through the `Files` enum in `spotidal/model/helpers/type/file.py`
(`Files.SETTINGS.load()` / `.save()`), never `open()` or `yaml` directly, and never
invent a new state path.

The SQLite database and the audio files live under the user's configured
`downloadPath` (default `~/Spotidal`), not in the repo.

## Do not touch

- `spotidal/web/` — contains only stale `__pycache__`; the sources were never
  committed. Treat as deleted; do not "restore" it from the `.pyc` files.
- `spotidal/model/config.py` — empty file, dead.
- `spotidal/Volumes/` — stray test fixtures that leaked into the package.
- `download/`, `dist/`, `.venv/`, `.cache*` — build/runtime junk.
- `credentials.yml`, `~/.config/spotidal/credentials.yml` — real secrets. Never read,
  print, or commit them.

## Verifying changes

**There are no tests, no CI, and no linter or formatter configured.** Do not claim a
change is verified because it imports. To check your work:

```bash
poetry run python -m compileall -q spotidal   # syntax
poetry run spotidal doctor all                # end-to-end over the real library
```

For anything touching menus or prompts, run `poetry run spotidal` and walk the path
by hand — the prompt layer is not exercised by any automated check.

## Where to go next

- [`docs/agents/architecture.md`](docs/agents/architecture.md) — module map, who calls whom.
- [`docs/agents/data-model.md`](docs/agents/data-model.md) — SQLite schema and the existing `MusicLibrary` API. **Read before adding any DB code.**
- [`docs/agents/workflows.md`](docs/agents/workflows.md) — sync, download, doctors, watcher, traced end to end.
- [`docs/agents/conventions.md`](docs/agents/conventions.md) — patterns to copy when adding a menu, a setting, or output.
- [`docs/agents/status.md`](docs/agents/status.md) — what is stale, broken, or in flight. **Read before trusting `README.md`.**
