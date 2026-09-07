import sqlite3
import urllib.parse
from pathlib import Path
from xml.sax.saxutils import quoteattr

# Rekordbox matches XML tracks against the collection by Location, so the paths
# written here must be the exact absolute mp3 paths already imported there.
FOLDER_NAME = "Spotidal"

# Windows/macOS-hostile characters, plus a leading dot that would make the
# playlist file invisible in the import dialog.
_UNSAFE = str.maketrans({"/": "_", ":": "_", "\\": "_", "*": "_", "?": "_",
                         '"': "_", "<": "_", ">": "_", "|": "_"})


def _safe_filename(name):
    return (name.translate(_UNSAFE).strip().lstrip(".") or "playlist")


def _location_url(path):
    return "file://localhost" + urllib.parse.quote(str(path), safe="/")


class RekordboxExport:
    """Rebuilds the library's playlists as files rekordbox can import."""

    def __init__(self, database_path, root_path):
        self.database_path = Path(database_path).expanduser().resolve()
        self.root_path = Path(root_path).expanduser().resolve()

    def _playlists(self):
        """Playlist name -> ordered, de-duplicated absolute mp3 paths on disk."""
        connection = sqlite3.connect(self.database_path)
        try:
            playlists = []
            rows = connection.execute(
                "SELECT playlist_id, name FROM playlists ORDER BY name"
            ).fetchall()
            for playlist_id, name in rows:
                tracks = []
                seen = set()
                for track_id, path in connection.execute(
                    "SELECT pt.track_id, f.path FROM playlist_tracks pt "
                    "JOIN files f ON f.track_id = pt.track_id "
                    "WHERE pt.playlist_id = ? AND f.format = 'mp3' "
                    "AND f.missing_at IS NULL ORDER BY f.path",
                    (playlist_id,),
                ):
                    if track_id in seen:
                        continue
                    absolute = self.root_path / path
                    if not absolute.exists():
                        continue
                    seen.add(track_id)
                    tracks.append((track_id, absolute))
                playlists.append((name, tracks))
            return playlists
        finally:
            connection.close()

    def _track_metadata(self, track_ids):
        connection = sqlite3.connect(self.database_path)
        try:
            metadata = {}
            for track_id in track_ids:
                row = connection.execute(
                    "SELECT title, artist, album, genre, year FROM tracks "
                    "WHERE track_id = ?",
                    (track_id,),
                ).fetchone()
                metadata[track_id] = row or (None, None, None, None, None)
            return metadata
        finally:
            connection.close()

    def export_m3u8(self, output_path):
        """One .m3u8 per playlist. Simple, but re-importing duplicates them."""
        output_path = Path(output_path).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        written, skipped = [], []
        for name, tracks in self._playlists():
            if not tracks:
                skipped.append(name)
                continue
            target = output_path / (_safe_filename(name) + ".m3u8")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("#EXTM3U\n")
                for _, absolute in tracks:
                    handle.write(f"{absolute}\n")
            written.append(target)
        return {"written": written, "skipped": skipped}

    def export_xml(self, output_path, folder_name=FOLDER_NAME):
        """A single rekordbox.xml holding every playlist under one folder.

        Imports the whole tree in one action and carries per-track metadata,
        which .m3u8 cannot. rekordbox still reads the XML as a separate,
        read-only tree: re-exporting refreshes it on reload, but copying it back
        into the collection is a manual drag either way.
        """
        output_path = Path(output_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        playlists = [(name, tracks) for name, tracks in self._playlists() if tracks]
        skipped = [name for name, tracks in self._playlists() if not tracks]

        # rekordbox keys playlist entries by TrackID, so the collection is the
        # union of every playlist's tracks, numbered once.
        keys = {}
        collection = []
        for _, tracks in playlists:
            for track_id, absolute in tracks:
                if track_id not in keys:
                    keys[track_id] = len(keys) + 1
                    collection.append((track_id, absolute))
        metadata = self._track_metadata(keys)

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<DJ_PLAYLISTS Version="1.0.0">',
            '  <PRODUCT Name="rekordbox" Version="6.0.0" Company="AlphaTheta"/>',
            f'  <COLLECTION Entries="{len(collection)}">',
        ]
        for track_id, absolute in collection:
            title, artist, album, genre, year = metadata[track_id]
            attributes = [
                f'TrackID="{keys[track_id]}"',
                f"Name={quoteattr(title or absolute.stem)}",
                f"Artist={quoteattr(artist or '')}",
                f"Album={quoteattr(album or '')}",
                f"Genre={quoteattr(genre or '')}",
                'Kind="MP3 File"',
                f'Year="{year or ""}"',
                f"Location={quoteattr(_location_url(absolute))}",
            ]
            lines.append("    <TRACK " + " ".join(attributes) + "/>")
        lines += [
            "  </COLLECTION>",
            "  <PLAYLISTS>",
            '    <NODE Type="0" Name="ROOT" Count="1">',
            f'      <NODE Type="0" Name={quoteattr(folder_name)} Count="{len(playlists)}">',
        ]
        for name, tracks in playlists:
            lines.append(
                f'        <NODE Name={quoteattr(name)} Type="1" KeyType="0" '
                f'Entries="{len(tracks)}">'
            )
            for track_id, _ in tracks:
                lines.append(f'          <TRACK Key="{keys[track_id]}"/>')
            lines.append("        </NODE>")
        lines += ["      </NODE>", "    </NODE>", "  </PLAYLISTS>", "</DJ_PLAYLISTS>", ""]

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return {
            "path": output_path,
            "playlists": len(playlists),
            "tracks": len(collection),
            "skipped": skipped,
        }
