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
