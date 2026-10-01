# Conventions

Patterns taken from the existing code. Match them; this codebase has no formatter or
linter to correct you.

## Terminal output

Never `print()` a raw string. All output goes through `Text`:

```python
from spotidal.view.text import Text as t

print(t.busy(f"download dir: {path}"))
print(t.warning("TIDAL refresh token rejected"))
print(t.error(f"unable to authenticate with TIDAL: {e}"))
```

Available: `log`, `log_grey`, `busy`, `error`, `warning`, `grey`, `red`, `u`, `b`,
`track`, `display_selection`, `display_selection_table`. The `Text as t` alias is used
everywhere — keep it.

Inside a doctor, use the `DoctorReport` methods instead (`report.ok/.warn/.fail/.step`),
so the result is counted toward the exit code.

## Adding a menu entry

Menus are classes in `spotidal/view/prompt.py`. Each declares its options as **class
constants**, collects them in an `*_OPT` list, and returns the chosen string from
`display()`. The controller then branches on the same constants.

```python
class UtilsMenu(MenuBase):
    MY_NEW_ACTION = "do the new thing"
    LOCAL_FILES_OPT = [DOCTOR_MP3_QUALITY, MY_NEW_ACTION, ...]
```

Three steps, all required:

1. Add the constant to the menu class.
2. Add it to the relevant `*_OPT` list (the Utils menu is grouped into `PLAYLISTS_OPT`,
   `DOWNLOAD_OPT`, `LOCAL_FILES_OPT`, `DATABASE_OPT`, `GENRES_OPT`, nested one level
   under `DOCTORS_OPT`, plus top-level `UTILS_OPT` for composite/routine actions — see
   below. An action may legitimately appear in more than one list.)
3. Handle it in `ControllerMain`, comparing against the constant, never a literal
   (`_default_selection` in `controller.py` is the reference for this — it imports
   `DefaultSelectionMenu` and compares against `DefaultSelectionMenu.VIEW` etc.,
   not raw strings, so relabeling a menu item can't silently break its handler).

Every menu passes `"mandatory": False` and `BACK_KEYBINDINGS` so the user can escape.
Keep that, and keep menu labels lowercase — the whole UI is lowercase.

**Where a new `utils` action goes**: composite actions that do several things in
sequence (like `sync database`, which chains reconcile → TIDAL refresh → repair) go
directly in top-level `UTILS_OPT`, so they're one click away. Narrow, single-purpose
commands go in the relevant domain submenu, nested under `doctors` if the submenu is
majority diagnostic checks. This was a deliberate reorganization (2026-09-25) — see
[status.md](status.md) for what moved and why.

**Menu labels should say what they compare**, not just what they do — several checks
in this app look similar but read from different sources (a TIDAL playlist mirror vs.
the live Spotify playlist vs. local disk vs. the local DB), and a vague label like
"refresh selection stats" invites assuming it's more complete than it is. Use `tidal
vs local`, `spotify vs local`, `disk vs db` etc. explicitly. See the "don't conflate"
table in [workflows.md](workflows.md) section 3 for why this matters in practice.

## Adding a setting

1. Add the key and its default to `DEFAULTS` in `spotidal/model/settings.py`.
2. Add a menu entry to the matching settings menu in `prompt.py`
   (`DownloadSettingsMenu`, `DatabaseSettingsMenu`, `NotificationsSettingsMenu`,
   `TidekeeperSettingsMenu`).
3. Handle it in the corresponding `ControllerMain` mutator.

Settings under the `"tidekeeper"` sub-dict are forwarded to the external downloader —
adding a key there only works if the binary understands it.

Read and write settings through `Files.SETTINGS.load()` / `.save()`, and always guard
against a missing key: users have older settings files on disk.

## Persisted files

Everything under `~/.config/spotidal/` goes through the `Files` enum in
`spotidal/model/helpers/type/file.py`:

```python
from spotidal.model.helpers.type.file import Files

settings = Files.SETTINGS.load() or {}
Files.SELECTION.save(list(selection))
```

The enum owns the path, the extension, and the JSON/YAML choice. Never open these
files directly and never hardcode `~/.config/spotidal/...`.

**Exception: logs and review-queue reports.** Diagnostic/report artifacts that aren't
application *state* — doctor run logs (`LOG_DIR` in `doctor.py`), the
playlist-consistency audit's CSVs (`NOT_FOUND_REVIEW_CSV` /
`ALBUM_DIFF_REVIEW_CSV` / `TIDAL_DIFF_REVIEW_CSV` in `webui/server.py`) — are plain
module-level `Path("~/.config/spotidal/logs/...")` constants, not `Files` enum
entries. `Files` is for state the app reads back as input (settings, credentials,
selection); a CSV that's overwritten wholesale on every audit run and only ever read
back by the same feature's own review UI doesn't need the enum's save/load
abstraction. Follow this precedent for a new report-style artifact rather than
forcing it into `Files`.

## Subprocesses

Call external binaries with a list of arguments, a timeout, and structured output
(`-of json` for ffprobe). Never build a shell string, never parse human-readable
terminal output. `_ffprobe_stream_info()` in `doctor.py` is the reference.

## Code style

- 4-space indent, `snake_case`, double quotes predominate.
- Type annotations are rare — a few (`model: Model`) exist, most functions have none.
  Do not add annotations to untyped modules just to add them.
- Private helpers are prefixed with `_`.
- Imports are relative inside `spotidal/model/` (`from .helpers...`), absolute from the
  controller (`from spotidal.model.model import Model`). Follow the file you are in.
- Errors that reach the user should be caught and rendered with `t.error(...)`; a
  traceback escaping into the menu loop is a bug.
