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
    year INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
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
"""


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
            playlist_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(playlists)")
            }
            if "total_tracks" not in playlist_columns:
                connection.execute("ALTER TABLE playlists ADD COLUMN total_tracks INTEGER")
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
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
                "SELECT file_id FROM files WHERE track_id=? AND location_id=? AND format=? AND path<>?",
                (track_id, location_id, file_path.suffix.lower().lstrip("."), relative_path),
            ).fetchone()
            if existing_file:
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

    def save_playlist_membership(self, name, tidal_playlist_id, total_tracks, track_ids):
        playlist_id = self.upsert_playlist(
            name, tidal_playlist_id=tidal_playlist_id, total_tracks=total_tracks
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
        self, name, spotify_playlist_id=None, tidal_playlist_id=None, total_tracks=None
    ):
        now = _now()
        playlist_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"spotidal:playlist:{name}"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO playlists(playlist_id,name,spotify_playlist_id,tidal_playlist_id,total_tracks,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET spotify_playlist_id=COALESCE(excluded.spotify_playlist_id, playlists.spotify_playlist_id), tidal_playlist_id=COALESCE(excluded.tidal_playlist_id, playlists.tidal_playlist_id), total_tracks=COALESCE(excluded.total_tracks, playlists.total_tracks), updated_at=excluded.updated_at",
                (playlist_id, name, spotify_playlist_id, tidal_playlist_id, total_tracks, now, now),
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
                "SELECT playlist_id, total_tracks FROM playlists WHERE name = ?",
                (name,),
            ).fetchone()
            if not row or row[1] is None:
                return None
            playlist_id, total = row
            local = connection.execute(
                "SELECT COUNT(DISTINCT pt.track_id) FROM playlist_tracks pt "
                "JOIN files f ON f.track_id = pt.track_id "
                "WHERE pt.playlist_id = ? AND f.missing_at IS NULL",
                (playlist_id,),
            ).fetchone()[0]
        return {"total": total, "local": local, "missing": total - local}

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
