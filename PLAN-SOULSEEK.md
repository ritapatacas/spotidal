# Feature Plan: Soulseek as an alternate download backend

## 1. Overview

Add Soulseek (via the `slskd` REST API) as a second download backend alongside
TIDAL, selectable per-track or per-playlist from the existing interactive menu.
This is an extension of Spotidal, not a standalone tool: it uses the existing
menu, the existing `Files`-based config, and the existing SQLite library
schema. No new CLI, no new config file, no new database.

**Primary integration:** `slskd` REST API (requires a locally running `slskd`
instance — same category of external dependency as `ffmpeg` or
`tidal-dl-ng`/`tidekeeper`; see AGENTS.md "Hard requirements").
**Implementation language:** Python, using `requests` (already a dependency;
no new HTTP client needed — `slskd`'s API is request/poll, not streaming).
**Initial scope:** search, candidate scoring, manual/automatic selection,
queueing, and transfer monitoring, wired into the existing `Download` flow.

The system must only be used to download content the user is authorized to
obtain. It must not bypass Soulseek access controls or platform limits.

## 2. Goals

- Search Soulseek (via `slskd`) using artist, title, album, and optional year.
- Normalize and compare candidate metadata.
- Apply hard filters and configurable ranking rules.
- Support manual approval and automatic selection modes.
- Queue selected files through `slskd` and monitor transfer status.
- Avoid re-downloading tracks already present in the local library
  (reuse `MusicLibrary.available_track_ids()`, same check TIDAL downloads use).
- Persist candidates/decisions/transfer state in the existing SQLite database.
- Keep selection logic (filtering/scoring) testable independently of the
  `slskd` client.

## 3. Non-goals for the MVP

- Music recognition from audio fingerprints.
- Automatic tagging beyond what the existing library indexer already does.
- Sharing or uploading files.
- Circumventing access controls, bans, or rate limits.
- Guaranteeing that a file's actual audio quality matches its filename or
  advertised bitrate.
- A dedicated web UI for Soulseek (the existing `webui/` stays
  library-search/DJ-suggestions only; Soulseek interaction stays in the
  InquirerPy menu).

## 4. User stories

1. As a user, from the existing download menu, I can choose Soulseek instead
   of TIDAL for a track or playlist.
2. As a user, I can configure accepted formats and minimum quality in the
   existing settings (`~/.config/spotidal/settings.json`).
3. As a user, I can see why a candidate was accepted, rejected, or ranked
   above another.
4. As a user, I can require approval before a download is queued, or let
   candidates above a score threshold queue automatically.
5. As a user, I see queued/active/completed/failed Soulseek transfers in the
   same place I already see TIDAL download progress.
6. As a user, I don't re-download tracks already in my library.
7. As a user, a Soulseek doctor check (mirroring the existing download
   doctor) tells me if `slskd` is reachable before I try to use it.

## 5. How this fits the existing architecture

Current flow (see `docs/agents/workflows.md`): `Download.by_td_id/by_url` →
`_find_tidal_track()` match → `helpers/td_downloader.py` shells out to the
`tidekeeper` binary → result tuple parsed back in `download.py` →
`MusicLibrary` updated.

`Download` has no backend abstraction today — everything assumes TIDAL and a
subprocess-based downloader. This plan introduces a minimal seam rather than
a parallel system:

```text
ControllerMain.download()/download_url()
    |
    v
Download  (spotidal/model/download.py)
    |-- backend = settings.downloadBackend  ("tidal" | "soulseek", per call or default)
    |
    |-- TIDAL path (existing, unchanged): helpers/td_downloader.py -> tidekeeper subprocess
    |
    '-- Soulseek path (new): helpers/soulseek_downloader.py -> slskd REST client
            |-- search        -> slskd /api/v0/searches
            |-- candidates    -> normalize + filter + score
            |-- queue_download -> slskd /api/v0/transfers/downloads/{username}
            '-- poll transfer -> slskd /api/v0/transfers/downloads
```

### Components (new files, following existing module layout)

- `spotidal/model/helpers/slskd_client.py` — thin `requests`-based wrapper
  around the `slskd` REST API: auth header, timeouts, bounded retries on
  transient failures. No new dependency; mirrors how `discogs.py` and
  `genre.py` already wrap external HTTP APIs with `requests`.
- `spotidal/model/helpers/soulseek_selection.py` — pure functions: hard
  filters, scoring, tie-breaking. No I/O, so it's unit-testable without a
  running `slskd` or network access — this is the one place genuinely worth
  automated tests given "no tests" is otherwise the project norm
  (AGENTS.md "Verifying changes").
- `spotidal/model/helpers/soulseek_downloader.py` — orchestrates
  search → filter/score → (approve) → queue → poll, called from `Download`
  the same way `td_downloader.download_url()` is called today. Produces a
  result shape compatible with what `download.py` already expects, or
  `download.py`'s per-track loop is adjusted to branch on backend before
  interpreting the result (small, local change — not a full rewrite of
  `Download`).

## 6. Selection workflow

1. Check the local library for an existing match
   (`MusicLibrary.available_track_ids()` — reused, not reimplemented).
2. Submit a search through `slskd`.
3. Collect candidate results (bounded by configured timeout/result limit).
4. Normalize candidate fields (artist, title, extension, bitrate, duration,
   size, username, availability).
5. Apply hard rejection rules.
6. Score remaining candidates.
7. Sort by score, then deterministic tie-breakers.
8. Manual mode: present ranked candidates with reasons via InquirerPy,
   same interaction pattern as existing match-review prompts in
   `spotidal/view/prompt.py`.
9. Automatic mode: queue the highest-ranked candidate meeting the threshold.
10. Poll transfer state until terminal; update the download record.
11. On completion, run the file through the same post-download step TIDAL
    downloads use today (library indexing) — no separate "LibraryFile" model.

### Hard filters

- Unsupported/disallowed file extension.
- MP3 bitrate below configured minimum, when bitrate is available.
- File size outside configured bounds.
- Duration outside configured bounds, when duration is available (compare
  against the Spotify track's known duration, already available at request
  time — this project already has it, unlike a from-scratch tool).
- Exact duplicate already present in the library.
- Missing required metadata, if policy requires it.

Missing metadata is handled explicitly per `unknown_metadata_policy`: reject,
allow with penalty, or require manual approval. Never silently pass unknowns.

### Ranking

| Signal | Example weight | Notes |
|---|---:|---|
| Exact artist/title match | 30 | Normalized text compare, not filename-only |
| Preferred format | 25 | e.g. FLAC preferred over lossy |
| Quality metadata | 20 | Only when bitrate/sample rate present and meaningful |
| Album/year match | 10 | Optional; shouldn't block single-track searches |
| Availability | 10 | Prefer candidates reported online |
| Transfer speed | 5 | Only if `slskd` exposes a reliable estimate |

Weights are configurable starting defaults. Normalize/cap so the total is
predictable, and surface the score breakdown to the user.

**Tie-breakers:** exact metadata match, preferred format, known duration,
availability, then stable lexical ordering. No randomness.

## 7. Configuration

Extend the existing `settings.json` (via the `Files` enum — no new config
file, per AGENTS.md "never invent a new state path"):

```json
{
  "downloadBackend": "tidal",
  "soulseek": {
    "baseUrl": "http://localhost:5030",
    "apiKeyEnv": "SLSKD_API_KEY",
    "searchTimeoutSeconds": 30,
    "maxResults": 100,
    "selectionMode": "manual",
    "minimumScore": 70,
    "allowedFormats": ["flac", "mp3"],
    "preferredFormatOrder": ["flac", "mp3"],
    "minimumMp3Bitrate": 320,
    "minSizeMb": 1,
    "maxSizeMb": 150,
    "durationToleranceSeconds": 8,
    "unknownMetadataPolicy": "manual_review",
    "maxConcurrentDownloads": 2
  }
}
```

The `slskd` API key is read from an environment variable
(`SLSKD_API_KEY`), never written into `settings.json` or logged — same rule
already in place for TIDAL/Spotify credentials (`credentials.yml` is
never read/printed/committed per AGENTS.md). Validate config at startup;
surface a clear error if `slskd` is unreachable rather than failing deep in
the download loop.

## 8. Data model changes

Extend the existing schema additively (per `docs/agents/data-model.md`'s
migration convention — `CREATE TABLE IF NOT EXISTS` / tracked migrations),
no parallel library model:

- `files.source` (nullable TEXT, e.g. `"tidal"` / `"soulseek"`) — which
  backend produced the file. Mirrors the pattern already used by
  `harvest_log.source` for metadata harvesting.
- New table `soulseek_candidates` (or similar): one row per search result
  considered for a track — `track_id`, `username`, `remote_path`, `filename`,
  `extension`, `size_bytes`, `bitrate`, `duration_seconds`, `availability`,
  `score`, `score_breakdown` (JSON), `rejection_reasons` (JSON), `selected`,
  `slskd_transfer_id`, `status`, `started_at`, `completed_at`, `error`.
  This is the one genuinely new table — existing `tracks`/`files` have no
  slot for per-candidate search/transfer bookkeeping, and that history is
  worth keeping for retry/debugging. Foreign key to `tracks.track_id`.

No separate `TrackRequest`/`Search`/`Download`/`LibraryFile` tables — those
collapse into the existing `tracks`/`files` tables plus the one new
`soulseek_candidates` table above.

## 9. `slskd` client requirements

Use `slskd`'s own API documentation for exact endpoint paths/payloads; do not
hard-code assumptions from examples found online — confirm during
implementation (M0 below).

Adapter methods (`slskd_client.py`):

- `search(query) -> SearchHandle`
- `get_search_results(search_id) -> list[Candidate]`
- `queue_download(candidate) -> TransferHandle`
- `get_transfer(transfer_id) -> TransferStatus`
- `cancel_transfer(transfer_id)`

Requirements:
- Keep `slskd`-specific response shapes inside this module only.
- Set connection and request timeouts (`requests` supports this directly).
- Retry transient failures with bounded exponential backoff.
- Avoid duplicate queue submissions on retry — idempotency check in
  `soulseek_downloader.py` before calling `queue_download`.
- Handle expired searches, unavailable users, rejected transfers, API errors.

## 10. Duplicate detection

1. Exact normalized artist + title + duration (when available) against
   `MusicLibrary` — same check already used before any TIDAL download starts.
2. Existing file path/size checks.
3. Optional content hash after download (future enhancement, not MVP).

Do not assume equal filenames mean equal audio, or different filenames mean
different audio. Keep duplicate decisions auditable; allow manual override.

## 11. User interface

No new CLI and no new web UI. Soulseek is reached through the existing
InquirerPy menu (`spotidal/controller/controller.py`):

- Add a backend choice where the user currently triggers a TIDAL download
  (or a settings toggle for a default backend, with override per action) —
  follow the existing `MainMenu` dispatch pattern.
  `ControllerMain.download()`/`download_url()` gain a backend branch.
- Candidate review (manual mode) reuses the existing match-review prompt
  style in `spotidal/view/prompt.py`: filename, username, format, size,
  bitrate, duration, availability, score + breakdown, rejection reasons,
  "already in library" flag.
- Transfer status shown via the same progress/log style used for TIDAL
  downloads today (`controller_main.py` download progress plumbing).
- `view` still never imports from `model` — Soulseek menu strings/choices
  stay plain data, same as every other menu.

## 12. Error handling and observability

- Distinguish no results, API failure, timeout, rejected transfer, local
  filesystem error.
- Persist state transitions in `soulseek_candidates`.
- Never log the `slskd` API key.
- A temporary `slskd` outage must not mark a download as permanently failed —
  surface it as retryable, consistent with how `TidalSessionStaleError` is
  already handled as recoverable in `td_downloader.py`.

## 13. Security and privacy

- `slskd` API key stays in an environment variable, never in `settings.json`
  or logs.
- Assume `slskd` is bound to localhost/trusted network; don't add remote
  exposure as part of this feature.
- Validate destination paths; restrict file operations to the configured
  `downloadPath`, same boundary TIDAL downloads already respect.
- Respect copyright, applicable law, and Soulseek/`slskd` terms.

## 14. Testing strategy

Given this project has no test suite or CI today (AGENTS.md "Verifying
changes"), keep automated tests scoped to the one pure-logic module:

- Unit tests for `soulseek_selection.py`: normalization, hard filters
  (including missing-metadata handling), scoring, tie-breaking, duplicate
  detection — this logic has no I/O and is cheap to test in isolation.
- No mocked-API integration test suite for MVP (out of step with the rest of
  the codebase); instead, manual acceptance testing against a real local
  `slskd` instance, same verification style already used for
  `poetry run spotidal doctor all`.

### Manual acceptance checklist

- Search for a known test track end-to-end through the menu.
- Compare several candidate results; confirm rejection reasons are visible.
- Queue a candidate in manual mode; confirm it appears in library after
  completion.
- Run automatic mode with a strict score threshold.
- Confirm an existing library file is not re-queued.
- Kill `slskd` mid-download; confirm the failure is surfaced as retryable,
  not a silent hang (same bar as the stuck-at-N% fix already made for
  TIDAL downloads).

## 15. Milestones

### M0 — Integration spike
- [ ] Confirm `slskd` installation/API version; document it in AGENTS.md's
      "Hard requirements" section alongside `tidekeeper`/`ffmpeg`.
- [ ] Verify authentication and a basic search round-trip.
- [ ] Capture representative search-result and transfer payloads.

### M1 — Client and selection logic
- [ ] `slskd_client.py`: search, results, queue, transfer status, cancel.
- [ ] `soulseek_selection.py`: normalization, hard filters, scoring,
      tie-breaking — with unit tests.
- [ ] `files.source` column + `soulseek_candidates` table (additive
      migration).

### M2 — Wire into `Download`
- [ ] `soulseek_downloader.py` orchestrating search → filter/score → queue →
      poll.
- [ ] Backend branch in `Download`/`ControllerMain.download()`.
- [ ] Manual-mode candidate review via existing prompt patterns.
- [ ] Settings: `downloadBackend` + `soulseek.*` block in `settings.json`.

### M3 — Automatic mode and hardening
- [ ] Automatic selection threshold.
- [ ] Duplicate-queue protection, retry/recovery for transient `slskd`
      failures.
- [ ] Soulseek doctor check (reachability) mirroring the existing download
      doctor.
- [ ] Update `docs/agents/workflows.md`, `architecture.md`, `status.md`.

## 16. Definition of done

A user can, from the existing menu, choose Soulseek for a track, review
ranked candidates with visible reasons, approve or auto-select one, have it
queued and monitored through `slskd`, and see it land in the library exactly
like a TIDAL download — without a second CLI, a second config file, or a
second database. Selection logic has unit tests; everything else is verified
manually against a real `slskd` instance, consistent with how the rest of
Spotidal is verified today.

## 17. Open questions

- Per-action backend choice, or a single default with override?
- Should FLAC always outrank MP3, or is format preference per-request
  configurable?
- Should unknown bitrate/duration trigger rejection or manual review by
  default?
- Should automatic mode fall back to the next candidate after a transfer
  failure, or stop and surface the failure?
