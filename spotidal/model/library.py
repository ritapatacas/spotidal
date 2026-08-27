import sqlite3
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
    bit_depth INTEGER, file_size INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE(location_id, path)
);
CREATE TABLE IF NOT EXISTS playlists (
    playlist_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    spotify_playlist_id TEXT, tidal_playlist_id TEXT, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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


def _year(value):
    try:
        return int(str(value)[:4]) if value else None
    except ValueError:
        return None


class MusicLibrary:
    def __init__(self, root_path):
        self.root_path = Path(root_path).expanduser().resolve()
        self.database_path = self.root_path / "database" / "library.db"
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
        return audio, tags, {
            "track_id": track_id,
            "title": _first(tags, "title") or file_path.stem,
            "artist": _first(tags, "artist") or "Unknown artist",
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
        with self._connect() as connection:
            location_id = connection.execute(
                "SELECT location_id FROM locations WHERE name = ?", (location_name,)
            ).fetchone()
            if location_id:
                location_id = location_id[0]
            else:
                location_id = uuid7()
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
            relative_path = file_path.relative_to(self.root_path).as_posix()
            connection.execute(
                "INSERT INTO files(track_id,location_id,format,path,filename,file_size,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(location_id,path) DO UPDATE SET track_id=excluded.track_id,updated_at=excluded.updated_at",
                (track_id, location_id, file_path.suffix.lower().lstrip("."), relative_path, file_path.name, file_path.stat().st_size, now, now),
            )
        if metadata["track_id"] != track_id:
            self.write_track_id(file_path, track_id)
        return track_id

    def upsert_playlist(self, name, spotify_playlist_id=None, tidal_playlist_id=None):
        now = _now()
        playlist_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"spotidal:playlist:{name}"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO playlists(playlist_id,name,spotify_playlist_id,tidal_playlist_id,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET spotify_playlist_id=COALESCE(excluded.spotify_playlist_id, playlists.spotify_playlist_id), tidal_playlist_id=COALESCE(excluded.tidal_playlist_id, playlists.tidal_playlist_id), updated_at=excluded.updated_at",
                (playlist_id, name, spotify_playlist_id, tidal_playlist_id, now, now),
            )
        return playlist_id

    def add_playlist_tracks(self, playlist_id, track_ids):
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO playlist_tracks(playlist_id,track_id) VALUES(?,?)",
                [(playlist_id, track_id) for track_id in set(track_ids)],
            )

    def associate_tidal_playlist(self, playlist, tidal_playlist_id):
        playlist_id = self.upsert_playlist(
            playlist.name, tidal_playlist_id=tidal_playlist_id
        )
        playlist_tracks = playlist.tracks()
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
