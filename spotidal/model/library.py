import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TXXX


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tracks (
    track_id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
    album TEXT, album_artist TEXT, isrc TEXT, spotify_id TEXT, tidal_id TEXT,
    year INTEGER, genre TEXT, style TEXT, bpm REAL, musical_key TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
    location_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, root_path TEXT NOT NULL,
    type TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    file_id INTEGER PRIMARY KEY, track_id TEXT NOT NULL REFERENCES tracks(track_id),
    location_id TEXT NOT NULL REFERENCES locations(location_id), format TEXT NOT NULL,
    path TEXT NOT NULL, filename TEXT NOT NULL, bitrate INTEGER, sample_rate INTEGER,
    bit_depth INTEGER, file_size INTEGER, missing_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(location_id, path)
);
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    spotify_playlist_id TEXT, tidal_playlist_id TEXT, total_tracks INTEGER,
    matched_tracks INTEGER, owner TEXT, folder_path TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL REFERENCES playlists(playlist_id),
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    PRIMARY KEY (playlist_id, track_id)
);
CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON tracks(isrc);
CREATE INDEX IF NOT EXISTS idx_tracks_spotify_id ON tracks(spotify_id);
CREATE INDEX IF NOT EXISTS idx_tracks_tidal_id ON tracks(tidal_id);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(location_id, path);
CREATE TABLE IF NOT EXISTS genre (
    genre_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS style (
    style_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS discogs_release (
    discogs_release_id INTEGER PRIMARY KEY,
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    discogs_id INTEGER NOT NULL, master_id INTEGER,
    confidence REAL, match_method TEXT, is_selected INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'pending',
    selection_method TEXT NOT NULL DEFAULT 'automatic',
    title TEXT, year INTEGER, label TEXT, catalog_number TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discogs_release_genre_style (
    discogs_release_id INTEGER NOT NULL
        REFERENCES discogs_release(discogs_release_id),
    genre_id INTEGER NOT NULL REFERENCES genre(genre_id),
    style_id INTEGER REFERENCES style(style_id),
    UNIQUE (discogs_release_id, genre_id, style_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_release_genre_no_style
    ON discogs_release_genre_style (discogs_release_id, genre_id)
    WHERE style_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_discogs_release_track
    ON discogs_release(track_id);
CREATE INDEX IF NOT EXISTS idx_discogs_release_discogs_id
    ON discogs_release(discogs_id);
CREATE TABLE IF NOT EXISTS final_genre (
    final_genre_id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS track_genre_style (
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    final_genre_id INTEGER NOT NULL REFERENCES final_genre(final_genre_id),
    style_id INTEGER REFERENCES style(style_id),
    UNIQUE (track_id, final_genre_id, style_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_genre_no_style
    ON track_genre_style (track_id, final_genre_id)
    WHERE style_id IS NULL;
CREATE TABLE IF NOT EXISTS harvest_log (
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    source TEXT NOT NULL DEFAULT 'discogs',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    PRIMARY KEY (track_id, source)
);
CREATE TABLE IF NOT EXISTS rym_release (
    rym_release_id INTEGER PRIMARY KEY,
    track_id TEXT NOT NULL REFERENCES tracks(track_id),
    rym_path TEXT NOT NULL,
    title TEXT,
    artist TEXT,
    year INTEGER,
    confidence REAL,
    match_method TEXT,
    is_selected INTEGER NOT NULL DEFAULT 1,
    review_status TEXT NOT NULL DEFAULT 'pending',
    selection_method TEXT NOT NULL DEFAULT 'automatic',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (track_id, rym_path)
);
CREATE INDEX IF NOT EXISTS idx_rym_release_track
    ON rym_release(track_id);
CREATE INDEX IF NOT EXISTS idx_rym_release_path
    ON rym_release(rym_path);
CREATE TABLE IF NOT EXISTS rym_release_genre (
    rym_release_id INTEGER NOT NULL
        REFERENCES rym_release(rym_release_id),
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('primary', 'secondary', 'descriptor')),
    UNIQUE (rym_release_id, name, kind)
);
"""

FINAL_GENRE_SEED = [
    "House", "Techno", "Trance", "Drum & Bass", "Electro",
    "Hip-Hop", "R&B", "Latin", "Disco", "Experimental",
]


def _recreate_track_genre_style(connection):
    connection.execute(
        """
        CREATE TABLE track_genre_style (
            track_id TEXT NOT NULL REFERENCES tracks(track_id),
            final_genre_id INTEGER NOT NULL REFERENCES final_genre(final_genre_id),
            style_id INTEGER REFERENCES style(style_id),
            UNIQUE (track_id, final_genre_id, style_id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX uq_track_genre_no_style
        ON track_genre_style (track_id, final_genre_id)
        WHERE style_id IS NULL
        """
    )


def uuid7():
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    value = (timestamp << 80) | (uuid.uuid4().int & ((1 << 76) - 1))
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0x3 << 62)
    value |= 0x2 << 62
    return str(uuid.UUID(int=value))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _first(tags, *keys):
    for key in keys:
        value = tags.get(key)
        if value:
            if isinstance(value, list):
                return value[0]
            if hasattr(value, "text"):
                return value.text[0] if value.text else None
            return value
    return None


_FILENAME_TAGS_PATTERN = re.compile(
    r"^\d+\s*[-.]\s*(?P<artist>.+?)\s*-\s*(?P<title>.+)$"
)


def _parse_filename_tags(stem):
    match = _FILENAME_TAGS_PATTERN.match(stem)
    if not match:
        return None, None
    return match.group("artist").strip(), match.group("title").strip()


def _normalize_match_text(text):
    text = re.sub(r"\(feat[^)]*\)", "", text or "", flags=re.IGNORECASE)
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.casefold().split())


# Guards import_file's read-check-insert of (isrc/tag -> track_id) against
# concurrent importers (startup reconcile thread, LibraryWatcher, downloads)
# racing and creating two track rows for the same file.
_IMPORT_LOCK = threading.Lock()


_CAMELOT_RE = re.compile(r"^(\d{1,2})([AB])$")


def _camelot_related(key):
    """Camelot-wheel keys that mix well with `key`: its relative major/minor
    (same number, other letter) and its two adjacent perfect fifths (number
    +-1, same letter)."""
    match = _CAMELOT_RE.match((key or "").strip().upper())
    if not match:
        return set()
    number, letter = int(match.group(1)), match.group(2)
    other_letter = "B" if letter == "A" else "A"
    related = {f"{number}{other_letter}"}
    for delta in (-1, 1):
        neighbor_number = ((number - 1 + delta) % 12) + 1
        related.add(f"{neighbor_number}{letter}")
    return related


def camelot_related(key):
    """Public, DB-free wrapper around `_camelot_related` for the search UI's
    Camelot wheel lookup: sorted list of keys that mix well with `key`."""
    return sorted(_camelot_related(key))


def _year(value):
    try:
        return int(str(value)[:4]) if value else None
    except ValueError:
        return None


class MusicLibrary:
    def __init__(self, root_path, database_path=None):
        self.root_path = Path(root_path).expanduser().resolve()
        self.database_path = (
            Path(database_path).expanduser().resolve()
            if database_path
            else self.root_path / "database" / "library.db"
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _migrate(self):
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(files)")
            }
            if "missing_at" not in columns:
                connection.execute("ALTER TABLE files ADD COLUMN missing_at TEXT")
            track_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(tracks)")
            }
            if "genre" not in track_columns:
                connection.execute("ALTER TABLE tracks ADD COLUMN genre TEXT")
            if "style" not in track_columns:
                connection.execute("ALTER TABLE tracks ADD COLUMN style TEXT")
            if "bpm" not in track_columns:
                connection.execute("ALTER TABLE tracks ADD COLUMN bpm REAL")
            if "musical_key" not in track_columns:
                connection.execute("ALTER TABLE tracks ADD COLUMN musical_key TEXT")
            if "review_reason" not in track_columns:
                connection.execute("ALTER TABLE tracks ADD COLUMN review_reason TEXT")
            if "reviewed_at" not in track_columns:
                connection.execute("ALTER TABLE tracks ADD COLUMN reviewed_at TEXT")
            playlist_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(playlists)")
            }
            if "total_tracks" not in playlist_columns:
                connection.execute("ALTER TABLE playlists ADD COLUMN total_tracks INTEGER")
            if "matched_tracks" not in playlist_columns:
                connection.execute("ALTER TABLE playlists ADD COLUMN matched_tracks INTEGER")
            if "owner" not in playlist_columns:
                connection.execute("ALTER TABLE playlists ADD COLUMN owner TEXT")
            if "folder_path" not in playlist_columns:
                connection.execute("ALTER TABLE playlists ADD COLUMN folder_path TEXT")
            release_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(discogs_release)")
            }
            if "review_status" not in release_columns:
                connection.execute(
                    "ALTER TABLE discogs_release ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending'"
                )
            if "selection_method" not in release_columns:
                connection.execute(
                    "ALTER TABLE discogs_release ADD COLUMN selection_method TEXT NOT NULL DEFAULT 'automatic'"
                )
            tgs_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(track_genre_style)")
            }
            if "genre_id" in tgs_columns:
                # v4 shipped track_genre_style against the Discogs `genre`
                # table; the final classification is its own taxonomy now.
                # Safe to recreate while the table is still empty.
                rows = connection.execute(
                    "SELECT track_id, genre_id, style_id FROM track_genre_style"
                ).fetchall()
                if rows:
                    raise RuntimeError(
                        "track_genre_style still references the Discogs genre table "
                        "and is not empty; migrate manually"
                    )
                connection.execute("DROP TABLE track_genre_style")
                _recreate_track_genre_style(connection)
            style_notnull = next(
                (
                    row[3] for row in connection.execute(
                        "PRAGMA table_info(track_genre_style)"
                    )
                    if row[1] == "style_id"
                ),
                0,
            )
            if style_notnull:
                # v5 shipped track_genre_style with a mandatory style; the
                # final classification allows genre-only rows (style NULL).
                if connection.execute(
                    "SELECT 1 FROM track_genre_style LIMIT 1"
                ).fetchone():
                    raise RuntimeError(
                        "track_genre_style has rows with a mandatory style; "
                        "migrate manually"
                    )
                connection.execute("DROP TABLE track_genre_style")
                _recreate_track_genre_style(connection)
            harvest_log_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(harvest_log)")
            }
            if "source" not in harvest_log_columns:
                # Pre-RYM harvest_log had PK (track_id) and only ever recorded
                # the Discogs harvest; backfill the new column instead of
                # losing the existing attempt counts.
                connection.execute(
                    """
                    CREATE TABLE harvest_log_v2 (
                        track_id TEXT NOT NULL REFERENCES tracks(track_id),
                        source TEXT NOT NULL DEFAULT 'discogs',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        last_attempt_at TEXT NOT NULL,
                        outcome TEXT NOT NULL,
                        PRIMARY KEY (track_id, source)
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO harvest_log_v2(track_id, source, attempts, last_attempt_at, outcome) "
                    "SELECT track_id, 'discogs', attempts, last_attempt_at, outcome FROM harvest_log"
                )
                connection.execute("DROP TABLE harvest_log")
                connection.execute("ALTER TABLE harvest_log_v2 RENAME TO harvest_log")
            for name in FINAL_GENRE_SEED:
                connection.execute(
                    "INSERT OR IGNORE INTO final_genre(name) VALUES(?)", (name,)
                )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(2, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(3, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(4, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(5, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(6, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(7, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(8, ?)",
                (_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(9, ?)",
                (_now(),),
            )

    def _metadata(self, file_path):
        if file_path.suffix.lower() == ".flac":
            audio = FLAC(file_path)
            tags = audio.tags or {}
            track_id = _first(tags, "TRACK_ID")
            isrc = _first(tags, "ISRC", "isrc")
        else:
            audio = EasyID3(file_path)
            tags = audio
            track_id = _first(ID3(file_path), "TXXX:TRACK_ID")
            isrc = _first(tags, "isrc")
        title = _first(tags, "title")
        artist = _first(tags, "artist")
        if not title or not artist:
            # Some downloads/imports carry no readable tags; many filenames
            # still follow "<track number> - <artist> - <title>" and are a
            # far better source than a bare "Unknown artist" placeholder.
            parsed_artist, parsed_title = _parse_filename_tags(file_path.stem)
            title = title or parsed_title or file_path.stem
            artist = artist or parsed_artist or "Unknown artist"
        return audio, tags, {
            "track_id": track_id,
            "title": title,
            "artist": artist,
            "album": _first(tags, "album"),
            "album_artist": _first(tags, "albumartist", "album artist"),
            "isrc": isrc,
            "year": _year(_first(tags, "date", "originaldate")),
        }

    def read_track_id(self, file_path):
        file_path = Path(file_path)
        if file_path.suffix.lower() == ".flac":
            return _first(FLAC(file_path).tags or {}, "TRACK_ID")
        return _first(ID3(file_path), "TXXX:TRACK_ID")

    def write_track_id(self, file_path, track_id):
        if file_path.suffix.lower() == ".flac":
            audio = FLAC(file_path)
            audio["TRACK_ID"] = track_id
            audio.save()
        else:
            audio = ID3(file_path)
            audio.delall("TXXX:TRACK_ID")
            audio.add(TXXX(encoding=3, desc="TRACK_ID", text=[track_id]))
            audio.save(v2_version=3)

    def import_file(
        self, file_path, location_name="main", location_type="local",
        spotify_id=None, tidal_id=None,
    ):
        file_path = Path(file_path).expanduser().resolve()
        audio, tags, metadata = self._metadata(file_path)
        now = _now()
        with _IMPORT_LOCK, self._connect() as connection:
            location_id = connection.execute(
                "SELECT location_id FROM locations WHERE name = ?", (location_name,)
            ).fetchone()
            if location_id:
                location_id = location_id[0]
                location_root = Path(connection.execute(
                    "SELECT root_path FROM locations WHERE location_id = ?",
                    (location_id,),
                ).fetchone()[0])
            else:
                location_id = uuid7()
                location_root = self.root_path
                connection.execute(
                    "INSERT INTO locations VALUES (?, ?, ?, ?, ?, ?)",
                    (location_id, location_name, str(self.root_path), location_type, now, now),
                )

            track_id = metadata["track_id"]
            if not track_id and metadata["isrc"]:
                row = connection.execute(
                    "SELECT track_id FROM tracks WHERE isrc = ?", (metadata["isrc"],)
                ).fetchone()
                track_id = row[0] if row else None
            track_id = track_id or uuid7()
            existing = connection.execute(
                "SELECT 1 FROM tracks WHERE track_id = ?", (track_id,)
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE tracks SET title=?, artist=?, album=?, album_artist=?, isrc=COALESCE(?, isrc), spotify_id=COALESCE(?, spotify_id), tidal_id=COALESCE(?, tidal_id), updated_at=? WHERE track_id=?",
                    (metadata["title"], metadata["artist"], metadata["album"], metadata["album_artist"], metadata["isrc"], spotify_id, tidal_id, now, track_id),
                )
            else:
                connection.execute(
                    "INSERT INTO tracks(track_id,title,artist,album,album_artist,isrc,spotify_id,tidal_id,year,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (track_id, metadata["title"], metadata["artist"], metadata["album"], metadata["album_artist"], metadata["isrc"], spotify_id, tidal_id, metadata["year"], now, now),
                )
            relative_path = file_path.relative_to(location_root).as_posix()
            connection.execute(
                "INSERT INTO files(track_id,location_id,format,path,filename,file_size,missing_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(location_id,path) DO UPDATE SET track_id=excluded.track_id,filename=excluded.filename,file_size=excluded.file_size,missing_at=NULL,updated_at=excluded.updated_at",
                (track_id, location_id, file_path.suffix.lower().lstrip("."), relative_path, file_path.name, file_path.stat().st_size, None, now, now),
            )
            existing_file = connection.execute(
                "SELECT file_id, path FROM files WHERE track_id=? AND location_id=? AND format=? AND path<>?",
                (track_id, location_id, file_path.suffix.lower().lstrip("."), relative_path),
            ).fetchone()
            # Re-point the row at the new path only when the previous file is
            # genuinely gone (rename/move). The same track legitimately exists
            # on several albums (Thriller vs Thriller 25 Deluxe); re-pointing
            # when both copies are on disk made the row flip between the two
            # paths on every scan, each scan reporting the dropped copy as
            # "added" - the endless "6 added" in the watcher log.
            if existing_file and not (Path(location_root).expanduser() / existing_file[1]).is_file():
                connection.execute(
                    "DELETE FROM files WHERE file_id = (SELECT file_id FROM files WHERE location_id=? AND path=?)",
                    (location_id, relative_path),
                )
                connection.execute(
                    "UPDATE files SET path=?, filename=?, file_size=?, missing_at=NULL, updated_at=? WHERE file_id=?",
                    (relative_path, file_path.name, file_path.stat().st_size, now, existing_file[0]),
                )
        if metadata["track_id"] != track_id:
            self.write_track_id(file_path, track_id)
        return track_id

    def locations(self):
        with self._connect() as connection:
            return connection.execute(
                "SELECT location_id, name, root_path, type FROM locations"
            ).fetchall()

    def available_tidal_ids(self, tidal_ids):
        tidal_ids = list(tidal_ids)
        if not tidal_ids:
            return set()
        placeholders = ",".join("?" for _ in tidal_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT tracks.tidal_id, locations.root_path, files.path "
                f"FROM tracks JOIN files ON files.track_id = tracks.track_id "
                f"JOIN locations ON locations.location_id = files.location_id "
                f"WHERE tracks.tidal_id IN ({placeholders}) "
                "AND files.missing_at IS NULL",
                [str(tidal_id) for tidal_id in tidal_ids],
            ).fetchall()
        return {str(tidal_id) for tidal_id, _, _ in rows}

    def available_track_id_map(self, tracks):
        """Match TIDAL tracks against the local library.

        Returns {tidal_id: local_track_id} for every input track we can
        confidently match locally. This is the single source of truth for
        "do we have this track" - both `available_track_ids` and playlist
        membership caching (`save_playlist_membership`) must derive from it,
        or the two can silently disagree on what's "local".
        """
        tracks = list(tracks)
        if not tracks:
            return {}
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT tracks.track_id, tracks.tidal_id, tracks.title, tracks.artist, "
                "tracks.album, files.filename "
                "FROM tracks JOIN files ON files.track_id = tracks.track_id "
                "WHERE files.missing_at IS NULL"
            ).fetchall()
            available = [
                (
                    track_id,
                    str(tidal_id) if tidal_id is not None else None,
                    _normalize_match_text(title),
                    artist.casefold(),
                    (album or "").casefold(),
                    filename.casefold(),
                )
                for track_id, tidal_id, title, artist, album, filename in rows
            ]
            available_by_tidal_id = {row[1]: row[0] for row in available if row[1]}
            result = {}
            now = _now()
            for track in tracks:
                tidal_id = str(track.id)
                if tidal_id in available_by_tidal_id:
                    # A known tidal_id is a stronger signal than title text,
                    # which can diverge in punctuation/casing from local tags.
                    result[tidal_id] = available_by_tidal_id[tidal_id]
                    continue
                artists = getattr(track, "artists", []) or []
                artist_names = {
                    getattr(artist, "name", str(artist)).casefold()
                    for artist in artists
                }
                artist = getattr(track, "artist", None)
                if artist:
                    artist_names.add(getattr(artist, "name", str(artist)).casefold())
                album = getattr(track, "album", None)
                album_name = getattr(album, "name", str(album) if album else "").casefold()
                title = _normalize_match_text(str(track.name))
                matches = [row for row in available if row[2] == title]
                matched_row = next(
                    (
                        row for row in matches
                        if row[3] in artist_names or row[4] == album_name
                    ),
                    matches[0] if len(matches) == 1 else None,
                )
                if matched_row:
                    result[tidal_id] = matched_row[0]
                    # We just proved this local track is this TIDAL track by
                    # title/artist/album; persist it so future lookups are an
                    # exact tidal_id match instead of repeating fuzzy work.
                    connection.execute(
                        "UPDATE tracks SET tidal_id = COALESCE(tidal_id, ?), updated_at = ? "
                        "WHERE track_id = ?",
                        (tidal_id, now, matched_row[0]),
                    )
        return result

    def available_track_ids(self, tracks):
        return set(self.available_track_id_map(tracks).keys())

    def save_playlist_membership(
        self, name, tidal_playlist_id, total_tracks, track_ids, matched_tracks=None
    ):
        playlist_id = self.upsert_playlist(
            name, tidal_playlist_id=tidal_playlist_id, total_tracks=total_tracks,
            matched_tracks=matched_tracks,
        )
        self.add_playlist_tracks(playlist_id, track_ids)

    def tracks_missing_tidal_id(self):
        with self._connect() as connection:
            return connection.execute(
                "SELECT track_id, title, artist, album FROM tracks "
                "WHERE tidal_id IS NULL ORDER BY title"
            ).fetchall()

    def set_tidal_id(self, track_id, tidal_id):
        with self._connect() as connection:
            connection.execute(
                "UPDATE tracks SET tidal_id=?, updated_at=? WHERE track_id=?",
                (str(tidal_id), _now(), track_id),
            )

    def genre_scan_rows(self, track_ids=None):
        with self._connect() as connection:
            query = (
                "SELECT t.track_id, t.title, t.artist, t.album, t.isrc, t.genre, "
                "f.format, f.path, l.root_path "
                "FROM tracks t "
                "JOIN files f ON f.track_id = t.track_id "
                "JOIN locations l ON l.location_id = f.location_id "
                "WHERE f.missing_at IS NULL"
            )
            params = []
            if track_ids:
                placeholders = ",".join("?" for _ in track_ids)
                query += f" AND t.track_id IN ({placeholders})"
                params = list(track_ids)
            return connection.execute(query + " ORDER BY t.album, t.title", params).fetchall()

    def final_genres(self):
        with self._connect() as connection:
            return connection.execute(
                "SELECT g.name, COUNT(tgs.track_id) FROM final_genre g "
                "LEFT JOIN track_genre_style tgs USING(final_genre_id) "
                "GROUP BY g.final_genre_id ORDER BY g.name"
            ).fetchall()

    def final_genre_styles(self, genre_name=None):
        with self._connect() as connection:
            query = (
                "SELECT g.name, COALESCE(s.name, '(no style)'), COUNT(*) "
                "FROM track_genre_style tgs "
                "JOIN final_genre g USING(final_genre_id) "
                "LEFT JOIN style s USING(style_id)"
            )
            params = []
            if genre_name:
                query += " WHERE g.name = ?"
                params = [genre_name]
            query += " GROUP BY g.name, s.name ORDER BY g.name, s.name"
            return connection.execute(query, params).fetchall()

    def add_final_genre(self, name):
        name = (name or "").strip()
        if not name:
            return None, False
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT final_genre_id FROM final_genre WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                return existing[0], False
            cursor = connection.execute(
                "INSERT INTO final_genre(name) VALUES(?)", (name,)
            )
        return cursor.lastrowid, True

    def add_style(self, name):
        name = (name or "").strip()
        if not name:
            return None, False
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT style_id FROM style WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                return existing[0], False
            cursor = connection.execute("INSERT INTO style(name) VALUES(?)", (name,))
        return cursor.lastrowid, True

    def playlist_names(self):
        with self._connect() as connection:
            return [
                row[0] for row in connection.execute(
                    "SELECT name FROM playlists ORDER BY name COLLATE NOCASE"
                )
            ]

    def track_ids_for_playlists(self, names):
        names = list(names or [])
        if not names:
            return []
        placeholders = ",".join("?" for _ in names)
        with self._connect() as connection:
            return [
                row[0] for row in connection.execute(
                    f"SELECT DISTINCT pt.track_id FROM playlist_tracks pt "
                    f"JOIN playlists p USING(playlist_id) WHERE p.name IN ({placeholders})",
                    names,
                )
            ]

    def import_rekordbox_metadata(self, entries):
        """Matches rekordbox track exports against local files by absolute
        path and stamps tracks.bpm/tracks.musical_key. `entries` is an
        iterable of (file_path, bpm, key); either value may be None.
        Returns {"matched", "unmatched"}.
        """
        matched = 0
        unmatched = 0
        now = _now()
        with self._connect() as connection:
            locations = connection.execute(
                "SELECT location_id, root_path FROM locations"
            ).fetchall()
            resolved_locations = [
                (location_id, Path(root_path).expanduser().resolve())
                for location_id, root_path in locations
            ]
            for file_path, bpm, key in entries:
                if bpm is None and key is None:
                    continue
                try:
                    file_path = Path(file_path).expanduser().resolve()
                except (OSError, RuntimeError, ValueError):
                    unmatched += 1
                    continue
                track_id = None
                for location_id, root_path in resolved_locations:
                    try:
                        relative = file_path.relative_to(root_path).as_posix()
                    except ValueError:
                        continue
                    row = connection.execute(
                        "SELECT track_id FROM files WHERE location_id=? AND path=?",
                        (location_id, relative),
                    ).fetchone()
                    if row:
                        track_id = row[0]
                        break
                if not track_id:
                    unmatched += 1
                    continue
                connection.execute(
                    "UPDATE tracks SET bpm=COALESCE(?, bpm), "
                    "musical_key=COALESCE(?, musical_key), updated_at=? "
                    "WHERE track_id=?",
                    (bpm, key, now, track_id),
                )
                matched += 1
        return {"matched": matched, "unmatched": unmatched}

    def search_filter_options(self):
        """Distinct values for the search UI's dropdowns."""
        with self._connect() as connection:
            genres = [
                row[0] for row in connection.execute(
                    "SELECT DISTINCT genre FROM tracks WHERE genre IS NOT NULL "
                    "AND genre <> '' ORDER BY genre COLLATE NOCASE"
                )
            ]
            styles = [
                row[0] for row in connection.execute(
                    "SELECT DISTINCT style FROM tracks WHERE style IS NOT NULL "
                    "AND style <> '' ORDER BY style COLLATE NOCASE"
                )
            ]
            keys = [
                row[0] for row in connection.execute(
                    "SELECT DISTINCT musical_key FROM tracks "
                    "WHERE musical_key IS NOT NULL ORDER BY musical_key"
                )
            ]
            playlists = [
                row[0] for row in connection.execute(
                    "SELECT name FROM playlists ORDER BY name COLLATE NOCASE"
                )
            ]
        return {"genres": genres, "styles": styles, "keys": keys, "playlists": playlists}

    def playlist_tree(self):
        """Playlists nested by folder_path, e.g. {"_items": [{"name":...,
        "count":...}], "_folders": {"parties": {"_items": [...], "_folders":
        {}}}}, for a directory-style browser (mirrors
        RekordboxExport._folder_tree's grouping). `count` is the number of
        locally available tracks in that playlist."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name, folder_path FROM playlists ORDER BY name COLLATE NOCASE"
            ).fetchall()
            counts = dict(connection.execute(
                "SELECT p.name, COUNT(DISTINCT pt.track_id) FROM playlists p "
                "JOIN playlist_tracks pt ON pt.playlist_id = p.playlist_id "
                "JOIN files f ON f.track_id = pt.track_id AND f.missing_at IS NULL "
                "GROUP BY p.name"
            ).fetchall())
        root = {"_items": [], "_folders": {}}
        for name, folder_path in rows:
            node = root
            if folder_path:
                for segment in folder_path.split("/"):
                    if not segment:
                        continue
                    node = node["_folders"].setdefault(
                        segment, {"_items": [], "_folders": {}}
                    )
            node["_items"].append({"name": name, "count": counts.get(name, 0)})
        return root

    def genre_counts(self):
        """[{"name", "count"}] of genres with at least one locally available
        track, for the search UI's Genres browser."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT t.genre, COUNT(DISTINCT t.track_id) FROM tracks t "
                "JOIN files f ON f.track_id = t.track_id AND f.missing_at IS NULL "
                "WHERE t.genre IS NOT NULL AND t.genre <> '' "
                "GROUP BY t.genre ORDER BY t.genre COLLATE NOCASE"
            ).fetchall()
        return [{"name": name, "count": count} for name, count in rows]

    def search_tracks(
        self, query=None, artist=None, title=None, bpm_min=None, bpm_max=None,
        key=None, genre=None, style=None, playlist=None, limit=300,
    ):
        """Local, available tracks matching the given filters (all optional
        and combinable). `query` is a loose title/artist/album match; `artist`
        and `title` narrow further, each against their own column only."""
        sql = (
            "SELECT DISTINCT t.track_id, t.title, t.artist, t.album, "
            "t.bpm, t.musical_key, t.genre, t.style, t.year "
            "FROM tracks t JOIN files f ON f.track_id = t.track_id "
            "AND f.missing_at IS NULL "
        )
        where = []
        params = []
        if playlist:
            sql += (
                "JOIN playlist_tracks pt ON pt.track_id = t.track_id "
                "JOIN playlists p ON p.playlist_id = pt.playlist_id "
            )
            where.append("p.name = ?")
            params.append(playlist)
        if query:
            where.append("(t.title LIKE ? OR t.artist LIKE ? OR t.album LIKE ?)")
            like = f"%{query}%"
            params += [like, like, like]
        if artist:
            where.append("t.artist LIKE ?")
            params.append(f"%{artist}%")
        if title:
            where.append("t.title LIKE ?")
            params.append(f"%{title}%")
        if bpm_min is not None:
            where.append("t.bpm >= ?")
            params.append(bpm_min)
        if bpm_max is not None:
            where.append("t.bpm <= ?")
            params.append(bpm_max)
        if key:
            where.append("t.musical_key = ?")
            params.append(key)
        if genre:
            where.append("t.genre = ?")
            params.append(genre)
        if style:
            where.append("t.style = ?")
            params.append(style)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.artist COLLATE NOCASE, t.title COLLATE NOCASE LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            {
                "track_id": row[0], "title": row[1], "artist": row[2],
                "album": row[3], "bpm": row[4], "key": row[5],
                "genre": row[6], "style": row[7], "year": row[8],
            }
            for row in rows
        ]

    def suggest_tracks(self, track_id, bpm_tolerance=0.06, limit=30):
        """Local, available tracks ranked by how well they'd mix with
        `track_id`: harmonic key compatibility (Camelot wheel), closeness in
        BPM (within `bpm_tolerance`, a fraction of the seed BPM), and sharing
        the seed's genre/style. Tracks with no signal in common are dropped.
        """
        with self._connect() as connection:
            seed = connection.execute(
                "SELECT bpm, musical_key, genre, style FROM tracks WHERE track_id = ?",
                (track_id,),
            ).fetchone()
            if not seed:
                return []
            seed_bpm, seed_key, seed_genre, seed_style = seed
            rows = connection.execute(
                "SELECT DISTINCT t.track_id, t.title, t.artist, t.album, "
                "t.bpm, t.musical_key, t.genre, t.style "
                "FROM tracks t JOIN files f ON f.track_id = t.track_id "
                "WHERE f.missing_at IS NULL AND t.track_id <> ? "
                "AND (t.bpm IS NOT NULL OR t.musical_key IS NOT NULL)",
                (track_id,),
            ).fetchall()
        related_keys = _camelot_related(seed_key)
        scored = []
        for row in rows:
            track_id_, title, artist, album, bpm, key, genre, style = row
            score = 0.0
            if seed_key and key:
                if key == seed_key:
                    score += 3
                elif key in related_keys:
                    score += 2
            if seed_bpm and bpm:
                drift = abs(bpm - seed_bpm) / seed_bpm
                if drift <= bpm_tolerance:
                    score += 2 * (1 - drift / bpm_tolerance)
            if seed_genre and genre and genre == seed_genre:
                score += 1
            if seed_style and style and style == seed_style:
                score += 1
            if score > 0:
                scored.append((score, {
                    "track_id": track_id_, "title": title, "artist": artist,
                    "album": album, "bpm": bpm, "key": key, "genre": genre,
                    "style": style, "score": round(score, 2),
                }))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def set_track_genre(self, track_id, genre, style):
        with self._connect() as connection:
            connection.execute(
                "UPDATE tracks SET genre=?, style=?, updated_at=? WHERE track_id=?",
                (genre, style, _now(), track_id),
            )

    def purge_orphan_tracks(self):
        with self._connect() as connection:
            orphan_ids = [
                row[0] for row in connection.execute(
                    "SELECT tracks.track_id FROM tracks "
                    "LEFT JOIN files ON files.track_id = tracks.track_id "
                    "WHERE files.file_id IS NULL"
                ).fetchall()
            ]
            if orphan_ids:
                placeholders = ",".join("?" for _ in orphan_ids)
                connection.execute(
                    f"DELETE FROM playlist_tracks WHERE track_id IN ({placeholders})",
                    orphan_ids,
                )
                connection.execute(
                    f"DELETE FROM tracks WHERE track_id IN ({placeholders})",
                    orphan_ids,
                )
        return len(orphan_ids)

    def repair_unknown_artists(self):
        with self._connect() as connection:
            total_unknown = connection.execute(
                "SELECT COUNT(*) FROM tracks WHERE artist = 'Unknown artist'"
            ).fetchone()[0]
            raw_samples = []
            for track_id, title in connection.execute(
                "SELECT track_id, title FROM tracks WHERE artist = 'Unknown artist' LIMIT 3"
            ).fetchall():
                file_rows = connection.execute(
                    "SELECT filename, missing_at FROM files WHERE track_id = ?",
                    (track_id,),
                ).fetchall()
                raw_samples.append(
                    f"track_id={track_id!r} title={title!r} files={file_rows!r}"
                )
            rows = connection.execute(
                "SELECT tracks.track_id, files.filename FROM tracks "
                "JOIN files ON files.track_id = tracks.track_id "
                "WHERE tracks.artist = 'Unknown artist'"
            ).fetchall()
            by_track = {}
            for track_id, filename in rows:
                by_track.setdefault(track_id, []).append(filename)
            repaired = 0
            unparsed_samples = []
            now = _now()
            for track_id, filenames in by_track.items():
                parsed_artist = parsed_title = None
                for filename in filenames:
                    parsed_artist, parsed_title = _parse_filename_tags(Path(filename).stem)
                    if parsed_artist and parsed_title:
                        break
                if parsed_artist and parsed_title:
                    connection.execute(
                        "UPDATE tracks SET title=?, artist=?, updated_at=? WHERE track_id=?",
                        (parsed_title, parsed_artist, now, track_id),
                    )
                    repaired += 1
                elif len(unparsed_samples) < 5:
                    unparsed_samples.append(filenames[0])
        return {
            "total_unknown": total_unknown,
            "with_files": len(by_track),
            "repaired": repaired,
            "unparsed_samples": unparsed_samples,
            "raw_samples": raw_samples,
        }

    def purge_temp_artifacts(self):
        # tidekeeper leaves orphaned "*.tmp.<n>.flac" files behind on
        # interrupted downloads; they still match the "*.flac" glob so they
        # were previously imported as garbage tracks (unreadable tags ->
        # title fell back to the raw filename, artist "Unknown artist").
        removed_files = 0
        removed_tracks = 0
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT files.file_id, files.track_id, locations.root_path, files.path "
                "FROM files JOIN locations ON locations.location_id = files.location_id "
                "WHERE files.filename LIKE '%.tmp.%'"
            ).fetchall()
            track_ids = set()
            for file_id, track_id, root_path, path in rows:
                track_ids.add(track_id)
                try:
                    (Path(root_path).expanduser() / path).unlink(missing_ok=True)
                except OSError:
                    pass
                connection.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
                removed_files += 1
            for track_id in track_ids:
                remaining = connection.execute(
                    "SELECT COUNT(*) FROM files WHERE track_id = ?", (track_id,)
                ).fetchone()[0]
                if remaining == 0:
                    connection.execute(
                        "DELETE FROM playlist_tracks WHERE track_id = ?", (track_id,)
                    )
                    connection.execute("DELETE FROM tracks WHERE track_id = ?", (track_id,))
                    removed_tracks += 1
        return {"files": removed_files, "tracks": removed_tracks}

    def reconcile_location(self, location_id, on_progress=None):
        changes = {"added": 0, "restored": 0, "missing": 0}
        with self._connect() as connection:
            location = connection.execute(
                "SELECT name, root_path, type FROM locations WHERE location_id=?", (location_id,)
            ).fetchone()
            tracked = connection.execute(
                "SELECT path, missing_at FROM files WHERE location_id=?", (location_id,)
            ).fetchall()
        if not location:
            return changes
        name, root_path, location_type = location
        root = Path(root_path).expanduser()
        if not root.is_dir():
            return changes
        # import_file() keys files by the resolved path relative to the
        # resolved root (it follows symlinks); use the same resolution here
        # or paths under a symlinked component never match `tracked`, and
        # reconcile "adds" the same files forever without actually
        # duplicating anything in the DB.
        resolved_root = root.resolve()
        actual = {
            path.resolve().relative_to(resolved_root).as_posix(): path
            for extension in ("*.flac", "*.mp3")
            for path in root.rglob(extension)
            if not path.name.startswith("._") and ".tmp." not in path.name
        }
        tracked = {path: missing_at for path, missing_at in tracked}
        imported = set()
        for relative_path, path in actual.items():
            try:
                self.import_file(path, location_name=name, location_type=location_type)
                imported.add(relative_path)
            except (OSError, ValueError, KeyError):
                continue
            finally:
                if on_progress:
                    on_progress()
        missing = set(tracked) - actual.keys()
        changes["added"] = sum(
            path in imported and path not in tracked for path in actual
        )
        changes["restored"] = sum(
            path in imported and tracked.get(path) is not None for path in actual
        )
        changes["missing"] = sum(tracked[path] is None for path in missing)
        if missing:
            with self._connect() as connection:
                connection.executemany(
                    "UPDATE files SET missing_at=CURRENT_TIMESTAMP WHERE location_id=? AND path=? AND missing_at IS NULL",
                    [(location_id, path) for path in missing],
                )
        return changes

    def reconcile_all(self, on_progress=None):
        changes = {"added": 0, "restored": 0, "missing": 0}
        for row in self.locations():
            location_changes = self.reconcile_location(row[0], on_progress=on_progress)
            for change_type in changes:
                changes[change_type] += location_changes[change_type]
        return changes

    def upsert_playlist(
        self, name, spotify_playlist_id=None, tidal_playlist_id=None,
        total_tracks=None, matched_tracks=None, owner=None,
    ):
        now = _now()
        playlist_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"spotidal:playlist:{name}"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO playlists(playlist_id,name,spotify_playlist_id,tidal_playlist_id,total_tracks,matched_tracks,owner,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET spotify_playlist_id=COALESCE(excluded.spotify_playlist_id, playlists.spotify_playlist_id), tidal_playlist_id=COALESCE(excluded.tidal_playlist_id, playlists.tidal_playlist_id), total_tracks=COALESCE(excluded.total_tracks, playlists.total_tracks), matched_tracks=COALESCE(excluded.matched_tracks, playlists.matched_tracks), owner=COALESCE(excluded.owner, playlists.owner), updated_at=excluded.updated_at",
                (playlist_id, name, spotify_playlist_id, tidal_playlist_id, total_tracks, matched_tracks, owner, now, now),
            )
        return playlist_id

    def add_playlist_tracks(self, playlist_id, track_ids):
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO playlist_tracks(playlist_id,track_id) VALUES(?,?)",
                [(playlist_id, track_id) for track_id in set(track_ids)],
            )

    def mark_missing(self, location_id, path):
        with self._connect() as connection:
            connection.execute(
                "UPDATE files SET missing_at=CURRENT_TIMESTAMP WHERE location_id=? AND path=?",
                (location_id, path),
            )

    def clear_playlist_tracks(self, name):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT playlist_id FROM playlists WHERE name = ?", (name,)
            ).fetchone()
            if row:
                connection.execute(
                    "DELETE FROM playlist_tracks WHERE playlist_id = ?", (row[0],)
                )

    def get_playlist_track_stats(self, name):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT playlist_id, total_tracks, matched_tracks FROM playlists WHERE name = ?",
                (name,),
            ).fetchone()
            if not row or row[1] is None:
                return None
            playlist_id, total, matched = row
            local = connection.execute(
                "SELECT COUNT(DISTINCT pt.track_id) FROM playlist_tracks pt "
                "JOIN files f ON f.track_id = pt.track_id "
                "WHERE pt.playlist_id = ? AND f.missing_at IS NULL",
                (playlist_id,),
            ).fetchone()[0]
        # matched_tracks counts covered TIDAL ids (several playlist entries can
        # legitimately share one local file); fall back to the per-file count
        # for rows cached before the column existed.
        local = max(local, matched) if matched is not None else local
        local = min(local, total)
        return {"total": total, "local": local, "missing": total - local}

    def audit_playlist(self, name):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT playlist_id, tidal_playlist_id, total_tracks, matched_tracks "
                "FROM playlists WHERE name = ?",
                (name,),
            ).fetchone()
            if not row:
                return {"synced": False}
            playlist_id, tidal_playlist_id, total, matched = row
            membership = connection.execute(
                "SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()[0]
            missing_tidal_id = connection.execute(
                "SELECT tracks.track_id, tracks.title, tracks.artist "
                "FROM playlist_tracks "
                "JOIN tracks ON tracks.track_id = playlist_tracks.track_id "
                "WHERE playlist_tracks.playlist_id = ? AND tracks.tidal_id IS NULL "
                "ORDER BY tracks.title COLLATE NOCASE",
                (playlist_id,),
            ).fetchall()
            missing_files = connection.execute(
                "SELECT tracks.track_id, tracks.title, tracks.artist "
                "FROM playlist_tracks "
                "JOIN tracks ON tracks.track_id = playlist_tracks.track_id "
                "WHERE playlist_tracks.playlist_id = ? AND NOT EXISTS ("
                "  SELECT 1 FROM files WHERE files.track_id = tracks.track_id "
                "  AND files.missing_at IS NULL"
                ") ORDER BY tracks.title COLLATE NOCASE",
                (playlist_id,),
            ).fetchall()
        return {
            "synced": True,
            "tidal_playlist_id": tidal_playlist_id,
            "total": total,
            "matched": matched,
            "membership": membership,
            "missing_tidal_id": missing_tidal_id,
            "missing_files": missing_files,
        }

    def file_details_for_tidal_id(self, tidal_id):
        with self._connect() as connection:
            return connection.execute(
                "SELECT tracks.track_id, tracks.title, tracks.artist, files.file_id, "
                "files.path, files.filename, files.missing_at, locations.root_path "
                "FROM tracks "
                "JOIN files ON files.track_id = tracks.track_id "
                "JOIN locations ON locations.location_id = files.location_id "
                "WHERE tracks.tidal_id = ?",
                (str(tidal_id),),
            ).fetchall()

    def purge_tidal_track(self, tidal_id):
        # Targeted cleanup for the download doctor's own test import; unlike
        # purge_orphan_tracks this only ever touches the given tidal_id.
        with self._connect() as connection:
            track_ids = [
                row[0] for row in connection.execute(
                    "SELECT track_id FROM tracks WHERE tidal_id = ?", (str(tidal_id),)
                ).fetchall()
            ]
            removed_files = 0
            track_removed = False
            for track_id in track_ids:
                removed_files += connection.execute(
                    "DELETE FROM files WHERE track_id = ?", (track_id,)
                ).rowcount
                remaining = connection.execute(
                    "SELECT COUNT(*) FROM files WHERE track_id = ?", (track_id,)
                ).fetchone()[0]
                if remaining == 0:
                    connection.execute(
                        "DELETE FROM playlist_tracks WHERE track_id = ?", (track_id,)
                    )
                    track_removed = bool(connection.execute(
                        "DELETE FROM tracks WHERE track_id = ?", (track_id,)
                    ).rowcount)
        return {"files": removed_files, "track_removed": track_removed}

    def associate_tidal_playlist(self, playlist, tidal_playlist_id, tracks=None):
        playlist_tracks = tracks if tracks is not None else playlist.tracks()
        playlist_id = self.upsert_playlist(
            playlist.name,
            tidal_playlist_id=tidal_playlist_id,
            total_tracks=len(playlist_tracks),
        )
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT track_id, title, artist FROM tracks"
            ).fetchall()
            matches = []
            for tidal_track in playlist_tracks:
                artists = {artist.name.casefold() for artist in tidal_track.artists}
                for track_id, title, artist in rows:
                    if title.casefold() == tidal_track.name.casefold() and artist.casefold() in artists:
                        connection.execute(
                            "UPDATE tracks SET tidal_id = COALESCE(tidal_id, ?), updated_at = ? WHERE track_id = ?",
                            (str(tidal_track.id), _now(), track_id),
                        )
                        matches.append(track_id)
                        break
            connection.executemany(
                "INSERT OR IGNORE INTO playlist_tracks(playlist_id,track_id) VALUES(?,?)",
                [(playlist_id, track_id) for track_id in set(matches)],
            )
