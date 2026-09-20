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
