# Feature Plan: Automated Soulseek Track Downloads

## 1. Overview

Build a service that searches Soulseek for tracks and automatically selects and queues files according to configurable quality, metadata, availability, and duplicate-detection rules.

**Primary integration:** `slskd` REST API  
**Implementation language:** Python  
**Initial scope:** Track search, candidate scoring, user review/automatic queueing, and download monitoring.

The system must only be used to download content the user is authorized to obtain. It should not bypass Soulseek access controls or platform limits.

## 2. Goals

- Search for tracks using artist, title, album, and optional year.
- Retrieve candidate files from Soulseek through `slskd`.
- Normalize and compare candidate metadata.
- Apply hard filters and configurable ranking rules.
- Support both automatic selection and manual approval.
- Queue selected files and monitor transfer status.
- Avoid downloading known duplicates.
- Persist searches, decisions, and download history.
- Make the selection logic testable independently of the Soulseek client.

## 3. Non-goals for the MVP

- Music recognition from audio fingerprints.
- Automatic tagging or library management beyond basic metadata.
- Sharing or uploading files.
- Circumventing access controls, bans, or rate limits.
- Guaranteeing that a file's actual audio quality matches its filename or advertised bitrate.

## 4. User stories

1. As a user, I can submit a track (artist and title) and receive matching Soulseek results.
2. As a user, I can configure accepted formats and minimum quality requirements.
3. As a user, I can see why a candidate was accepted, rejected, or ranked above another.
4. As a user, I can require approval before a download is queued.
5. As a user, I can enable automatic queueing when a candidate meets strict rules.
6. As a user, I can see queued, active, completed, and failed downloads.
7. As a user, I can prevent re-downloading files already in my library.
8. As a user, I can retry a failed search or transfer without losing its history.

## 5. Proposed architecture

```text
CLI / Web UI
    |
    v
Application service
    |---- Search service ------> slskd REST API ------> Soulseek network
    |---- Candidate evaluator
    |---- Selection policy
    |---- Download queue ------> slskd REST API
    |---- Transfer monitor ----> slskd REST API
    |
    v
SQLite (MVP) / PostgreSQL (later)
```

### Components

- **Client:** Typed wrapper around the `slskd` REST API; handles authentication, timeouts, retries, and response validation.
- **Search service:** Submits search terms and collects results until a configured timeout or result limit.
- **Normalizer:** Extracts and normalizes artist, title, album, extension, bitrate, duration, size, username, and availability where provided.
- **Evaluator:** Applies hard filters and computes a transparent score.
- **Queue manager:** Adds approved candidates to the `slskd` download queue and records returned identifiers.
- **Monitor:** Polls transfer state and updates local records.
- **Persistence:** Stores configuration, searches, candidates, decisions, and download state.
- **Interface:** Start with a CLI; keep application logic independent so a web UI can be added later.

## 6. Selection workflow

1. Validate the requested track and user configuration.
2. Check the local library for an existing match.
3. Submit a search through `slskd`.
4. Collect candidate results.
5. Normalize candidate fields.
6. Apply hard rejection rules.
7. Score the remaining candidates.
8. Sort by score, then apply deterministic tie-breakers.
9. In approval mode, present the ranked candidates and reasons.
10. In automatic mode, queue the highest-ranked candidate that meets the configured threshold.
11. Monitor the transfer and record its final state.
12. Optionally validate the downloaded file and update the local library index.

### Hard filters

Hard filters should reject a candidate regardless of score. Examples:

- Unsupported or disallowed file extension.
- MP3 bitrate below the configured minimum, when bitrate is available.
- File size outside configured bounds.
- Duration outside configured bounds, when duration is available.
- Exact duplicate already present.
- Missing required metadata, if the policy requires it.

Missing metadata should be handled explicitly: reject, allow with a penalty, or require manual approval. Do not silently treat unknown values as passing.

### Ranking

Use a configurable weighted score. Suggested MVP signals:

| Signal | Example weight | Notes |
|---|---:|---|
| Exact artist/title match | 30 | Compare normalized text; avoid relying on filename alone |
| Preferred format | 25 | Example: FLAC preferred over lossy formats |
| Quality metadata | 20 | Only score bitrate/sample rate when available and meaningful |
| Album/year match | 10 | Optional; should not block single-track searches unless configured |
| Availability | 10 | Prefer candidates reported as available/online |
| Transfer speed | 5 | Use only if a reliable estimate is exposed |

Weights are starting defaults, not a universal quality metric. Normalize or cap each signal so the total is predictable. Expose the score breakdown to the user.

**Tie-breakers:** exact metadata match, preferred format, known duration, availability, then stable lexical ordering. Do not use arbitrary randomness.

## 7. Configuration

Example YAML configuration:

```yaml
soulseek:
  base_url: "http://localhost:5030"
  # Load API key from an environment variable or secret store.
  api_key_env: "SLSKD_API_KEY"

search:
  timeout_seconds: 30
  max_results: 100

selection:
  mode: "manual" # manual | automatic
  minimum_score: 70
  allowed_formats: ["flac", "mp3"]
  preferred_format_order: ["flac", "mp3"]
  minimum_mp3_bitrate: 320
  min_size_mb: 1
  max_size_mb: 150
  duration_tolerance_seconds: 8
  unknown_metadata_policy: "manual_review"

downloads:
  max_concurrent: 2
  destination: "./downloads"
  skip_existing: true
```

Validate configuration at startup. Keep credentials out of source control and logs.

## 8. Data model

### TrackRequest
- `id`
- `artist`
- `title`
- `album` (optional)
- `year` (optional)
- `expected_duration_seconds` (optional)
- `created_at`
- `status`

### Search
- `id`
- `track_request_id`
- `query`
- `started_at`
- `completed_at`
- `status`
- `result_count`

### Candidate
- `id`
- `search_id`
- `username`
- `remote_path`
- `filename`
- `extension`
- `size_bytes`
- `bitrate` (nullable)
- `duration_seconds` (nullable)
- `availability` (nullable)
- `speed_estimate` (nullable)
- `score`
- `score_breakdown` (JSON)
- `rejection_reasons` (JSON)
- `selected` (boolean)

### Download
- `id`
- `candidate_id`
- `slskd_transfer_id`
- `status`
- `destination`
- `started_at`
- `completed_at`
- `error`

### LibraryFile
- `id`
- `path`
- `size_bytes`
- `artist` (nullable)
- `title` (nullable)
- `duration_seconds` (nullable)
- `content_hash` (nullable)
- `indexed_at`

## 9. API and integration requirements

Use the `slskd` API documentation for exact endpoint paths and payloads; do not hard-code assumptions from examples found online.

The adapter should provide application-level methods such as:

- `search(query) -> SearchHandle`
- `get_search_results(search_id) -> list[Candidate]`
- `queue_download(candidate) -> TransferHandle`
- `get_transfer(transfer_id) -> TransferStatus`
- `cancel_transfer(transfer_id)`

Requirements:
- Keep API-specific response models inside the adapter.
- Set connection and request timeouts.
- Retry transient failures with bounded exponential backoff.
- Avoid duplicate queue submissions on retry; use idempotency checks in the application layer.
- Handle expired searches, unavailable users, rejected transfers, and API errors.
- Confirm current `slskd` authentication and API behavior during implementation.

## 10. Duplicate detection

Use layered matching:

1. Exact normalized artist + title + duration (when available).
2. Existing file path and size checks.
3. Optional content hash after download.
4. Optional audio fingerprinting as a future enhancement.

Do not assume equal filenames mean equal audio, or different filenames mean different audio. Make duplicate decisions auditable and allow manual override.

## 11. User interface

### MVP CLI commands

```text
soulseek search "Artist" "Track"
soulseek queue <candidate-id>
soulseek downloads
soulseek config validate
soulseek library scan ./music
```

Search output should show:
- Filename and remote username
- Format, size, bitrate, and duration when known
- Availability and speed estimate when known
- Score and score breakdown
- Rejection reasons
- Whether the item is already in the library

### Later web UI

- Search form and candidate table
- Filters for format, quality, size, and duration
- Candidate comparison and approval
- Download queue with progress and error details
- Configuration editor with validation

## 12. Error handling and observability

- Distinguish no results, API failure, timeout, rejected transfer, and local filesystem error.
- Persist state transitions.
- Log request identifiers and internal IDs, but never API keys.
- Use structured logs.
- Prevent a temporary API outage from marking a download as permanently failed.
- Provide a clear retry action for recoverable failures.

## 13. Security and privacy

- Store the `slskd` API key in an environment variable or secret store.
- Bind the `slskd` service to localhost or a trusted network unless remote access is explicitly secured.
- Do not expose credentials in CLI output, logs, or error messages.
- Validate destination paths and prevent path traversal.
- Restrict file operations to configured download/library directories.
- Respect copyright, applicable law, and Soulseek/slskd terms.

## 14. Testing strategy

### Unit tests
- Filename and metadata normalization.
- Hard-filter behavior, including missing metadata.
- Score calculation and tie-breaking.
- Duplicate detection.
- Configuration validation.
- Destination path validation.

### Integration tests
- Mock `slskd` API responses for searches and transfers.
- Verify API errors, timeouts, retries, and malformed responses.
- Verify that a candidate is queued only once.
- Verify transfer state updates.

### Manual acceptance tests
- Search for a known test track.
- Compare several candidate results.
- Confirm rejection reasons are visible.
- Queue a candidate in manual mode.
- Run automatic mode with a strict score threshold.
- Confirm completed and failed transfers are represented correctly.
- Confirm an existing library file is not queued again.

## 15. Milestones

### M0 — Repository and integration spike
- [ ] Confirm `slskd` installation and API version.
- [ ] Verify authentication and basic search flow.
- [ ] Capture representative result and transfer payloads.
- [ ] Decide supported runtime and packaging.

### M1 — Search MVP
- [ ] Create project structure and configuration.
- [ ] Implement typed `slskd` client.
- [ ] Implement search submission and result collection.
- [ ] Normalize candidate metadata.
- [ ] Add CLI search output.

### M2 — Selection engine
- [ ] Implement hard filters.
- [ ] Implement configurable scoring.
- [ ] Add deterministic tie-breaking.
- [ ] Show score breakdown and rejection reasons.
- [ ] Add unit tests for policy behavior.

### M3 — Download queue
- [ ] Implement manual candidate approval.
- [ ] Queue selected candidate through `slskd`.
- [ ] Persist transfer identifiers and state.
- [ ] Add duplicate queue protection.
- [ ] Add CLI download status and cancellation.

### M4 — Automatic mode and library checks
- [ ] Implement automatic selection threshold.
- [ ] Add library scan and duplicate checks.
- [ ] Define behavior for unknown metadata.
- [ ] Add retry and recovery behavior.
- [ ] Add end-to-end acceptance tests.

### M5 — Hardening and optional UI
- [ ] Improve structured logging and diagnostics.
- [ ] Review security and path handling.
- [ ] Add packaging and deployment documentation.
- [ ] Evaluate whether a web UI is needed.

## 16. Definition of done

The MVP is complete when a user can submit a track, retrieve candidates, understand why each candidate was ranked or rejected, approve or automatically select a qualifying candidate, queue it through `slskd`, and observe the transfer state. The process must avoid duplicate queue submissions, handle expected API failures, and have automated tests for selection rules.

## 17. Open questions

- Should the first interface be CLI-only or include a web UI?
- Is the target deployment macOS, Windows, Linux, or Docker?
- Should FLAC always outrank MP3, or should the user define format preferences per request?
- Should unknown bitrate/duration trigger rejection or manual review?
- Should automatic mode queue one candidate or fall back to the next candidate after a transfer failure?
- Should the system manage a music library, or only download into a destination folder?
