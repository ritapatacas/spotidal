# Data model

All persistence lives in `spotidal/model/library.py` (`MusicLibrary`). It is plain
`sqlite3` — no ORM, despite `sqlalchemy` being declared in `pyproject.toml`.

The database file sits under the user's configured `downloadPath` (default
`~/Spotidal`), or at an explicit `database_path` passed to the constructor:

```python
library = MusicLibrary(root_path, database_path=None)
```

## Schema

Defined as the `SCHEMA` string near the top of `library.py` and applied by
`MusicLibrary._migrate()`. Migrations are **additive and idempotent**: every statement
is `CREATE TABLE IF NOT EXISTS`, with applied versions tracked in `schema_migrations`.
Add new migrations in that style; do not rewrite `SCHEMA` in a way that would need an
existing database to be dropped.

| Table | Key columns | Notes |
| --- | --- | --- |
| `schema_migrations` | `version`, `applied_at` | Migration bookkeeping. |
| `tracks` | `track_id` (uuid7 TEXT PK), `title`, `artist`, `album`, `isrc`, `spotify_id`, `tidal_id`, `year`, `genre`, `style`, `review_reason`, `reviewed_at` | The canonical track. Indexed on `isrc`, `spotify_id`, `tidal_id`. `review_reason`/`reviewed_at` back the playlist-consistency audit's "flagged" bucket — `NULL` means not flagged (or cleared on a later clean re-check); see [workflows.md](workflows.md) section 3. |
| `locations` | `location_id`, `name` UNIQUE, `root_path`, `type` | A scanned root directory. Supports multiple libraries (`otherLocations` in settings). |
| `files` | `file_id`, `track_id` → `tracks`, `location_id` → `locations`, `format`, `path`, `filename`, `bitrate`, `sample_rate`, `bit_depth`, `file_size`, `missing_at`, `UNIQUE(location_id, path)` | One row per physical file. One track may have both a FLAC and an MP3 row. |
| `playlists` | `playlist_id`, `name` **UNIQUE**, `spotify_playlist_id`, `tidal_playlist_id`, `total_tracks`, `matched_tracks` | See the caveat below. |
| `playlist_tracks` | `PRIMARY KEY (playlist_id, track_id)` | Membership only — **no position column**, playlist order is not stored. |
| `genre`, `style` | name tables | Vocabulary. |
| `discogs_release`, `discogs_release_genre_style` | | Cached Discogs lookups. |
| `rym_release`, `rym_release_genre` | | Cached Rate Your Music lookups. `rym_path` (e.g. `/release/album/artist/title/`) is the stable identity. |
| `harvest_log` | `PK (track_id, source)`, `attempts`, `outcome` | One row per (track, harvest). `source` is `'discogs'` or `'rym'`; the two harvests never share attempt counts. |
| `final_genre`, `track_genre_style` | | The resolved genre/style assigned to a track. |

### Two constraints to know before you write DB code

- **`playlists.name` is `NOT NULL UNIQUE`.** Playlist identity is therefore the *name*,
  not the Spotify/TIDAL id. Two distinct playlists sharing a name will collide. This is
  a known design weakness (see [status.md](status.md)); changing it requires a real
  migration that back-fills the external ids first.
- **`missing_at`** marks a file whose path disappeared from disk. A file only counts as
  locally present when `missing_at IS NULL`. Reconciliation sets and clears it; nothing
  deletes `files` rows on the strength of a single failed scan.
- **Discogs and RYM vocabulary never mixes.** `discogs_release_genre_style` and
  `rym_release_genre` are separate taxonomies on purpose — RYM labels (`primary`,
  `secondary`, `descriptor`) do not map 1:1 to Discogs genres/styles, and mixing them
  would pollute `bucket_for()` and the final classifications. Neither harvest writes to
  `tracks.genre`/`tracks.style` or to file tags; only `GenreFiller` does that.

## Existing `MusicLibrary` API — check here before adding a method

This is the most common source of duplicated work. These already exist:

**Playlists**
- `upsert_playlist(...)` — idempotent, returns the internal `playlist_id`.
- `add_playlist_tracks(playlist_id, track_ids)` — membership rows.
- `save_playlist_membership(...)` — higher-level combination of the two.
- `associate_tidal_playlist(playlist, tidal_playlist_id, tracks=None)`
- `clear_playlist_tracks(name)`, `playlist_names()`, `track_ids_for_playlists(names)`

**Reporting**
- `get_playlist_track_stats(name)` → `{"total", "local", "missing"}` — **`total`/`local`
  are counted against the TIDAL playlist mirror, not Spotify.** See the "don't conflate"
  table in [workflows.md](workflows.md) section 3 before using this for "is my library
  complete vs Spotify" — it isn't that.
- `audit_playlist(name)` — per-track detail, same TIDAL-mirror-vs-local basis as above.
- `file_details_for_tidal_id(tidal_id)`

**Review queue** (playlist-consistency audit; see [workflows.md](workflows.md) section 3)
- `find_track_by_isrc(isrc)` — primary lookup; ISRC alone is unreliable across TIDAL vs
  Spotify, callers should fall back to the next one.
- `find_tracks_by_title_like(title_fragment, limit=50)` — broad substring candidates,
  `ORDER BY LENGTH(title) ASC` so a short/common fragment's exact-length match isn't cut
  off by `limit` behind hundreds of longer titles that merely contain it.
- `flagged_tracks()` — every track with `review_reason IS NOT NULL`, for the `/review`
  webui page's Flagged tab.
- `set_review(track_id, reason)` — set (`reason` a string) or clear (`reason=None`)
  `review_reason`/`reviewed_at`.

**Tracks and files**
- `import_file(...)` — the single ingestion path for a file on disk.
- `available_track_ids(tracks)` / `available_track_id_map(tracks)` — what is already downloaded.
- `available_tidal_ids(tidal_ids)`
- `read_track_id(path)` / `write_track_id(path, track_id)` — the track id is stamped into the file's tags, which is how a moved file keeps its identity.
- `set_tidal_id`, `set_track_isrc`, `tracks_missing_tidal_id()`

**Maintenance**
- `reconcile_location(location_id, on_progress=None)` / `reconcile_all(on_progress=None)`
- `mark_missing(location_id, path)`
- `purge_orphan_tracks()`, `purge_temp_artifacts()`, `purge_tidal_track(tidal_id)`
- `repair_unknown_artists()`

**Genres**
- `final_genres()`, `final_genre_styles(genre_name=None)`, `add_final_genre(name)`,
  `add_style(name)`, `set_track_genre(track_id, genre, style)`, `genre_scan_rows(track_ids=None)`

## Counting rules for reports

When adding any "how many tracks have X" query, follow the established rules:

- Count with `COUNT(DISTINCT track_id)` — a track with two copies of the same format
  must not count twice.
- A file counts as local only when `missing_at IS NULL`.
- A track holding both FLAC and MP3 counts in both format tallies.
- Match on `files.track_id`, never on filename similarity. Filenames may be shown to the
  user for manual action, but are not evidence of identity.
