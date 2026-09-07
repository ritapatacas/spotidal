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
2. Add it to the relevant `*_OPT` list (the Utils menu is grouped into
   `PLAYLISTS_OPT`, `DOWNLOAD_OPT`, `LOCAL_FILES_OPT`, `DATABASE_OPT`, `GENRES_OPT` —
   an action may legitimately appear in more than one).
3. Handle it in `ControllerMain`, comparing against the constant, never a literal.

Every menu passes `"mandatory": False` and `BACK_KEYBINDINGS` so the user can escape.
Keep that, and keep menu labels lowercase — the whole UI is lowercase.

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
