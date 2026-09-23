#!/usr/bin/env python3
"""
Take every track successfully downloaded by download_missing_flac.py and put
it into a local library playlist called "attick", then report every track in
the library that isn't a member of any playlist.

Usage:
    poetry run python scripts/attick_playlist.py [--progress PATH] [--playlist-name attick]
"""
import argparse
import csv
from pathlib import Path

from spotidal.model.helpers.type.file import Files
from spotidal.model.library import MusicLibrary


def load_downloaded_tidal_ids(progress_path: Path):
    with open(progress_path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["result"] == "downloaded"]
    return [r["tidal_id"] for r in rows if r["tidal_id"]]


def open_library() -> MusicLibrary:
    settings = Files.SETTINGS.load() or {}
    flac_dir = settings.get("flacDirectory") or str(
        Path(settings.get("downloadPath", "~/Spotidal")).expanduser() / "flac"
    )
    root_path = Path(flac_dir).expanduser().parent
    return MusicLibrary(root_path, settings.get("databaseLocation"))


def add_to_playlist(library: MusicLibrary, playlist_name: str, tidal_ids):
    with library._connect() as connection:
        track_ids = []
        missing_tidal_ids = []
        for tidal_id in tidal_ids:
            row = connection.execute(
                "SELECT track_id FROM tracks WHERE tidal_id = ?", (tidal_id,)
            ).fetchone()
            if row:
                track_ids.append(row[0])
            else:
                missing_tidal_ids.append(tidal_id)

    playlist_id = library.upsert_playlist(playlist_name)
    library.add_playlist_tracks(playlist_id, track_ids)
    return track_ids, missing_tidal_ids


def report_orphan_tracks(library: MusicLibrary, out_path: Path):
    with library._connect() as connection:
        rows = connection.execute(
            "SELECT t.track_id, t.artist, t.title, t.album "
            "FROM tracks t "
            "WHERE t.track_id NOT IN (SELECT track_id FROM playlist_tracks) "
            "ORDER BY t.artist COLLATE NOCASE, t.title COLLATE NOCASE"
        ).fetchall()

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["track_id", "artist", "title", "album"])
        writer.writerows(rows)

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--progress",
        default="/Users/ritapatacas/sound-library/download_missing_flac_progress.csv",
        help="path to download_missing_flac.py's progress csv",
    )
    parser.add_argument("--playlist-name", default="attick")
    parser.add_argument(
        "--orphans-out",
        default="/Users/ritapatacas/sound-library/tracks_without_playlist.csv",
        help="where to write the list of tracks in the db that belong to no playlist",
    )
    parser.add_argument("--skip-playlist", action="store_true", help="only run the orphan report")
    parser.add_argument("--skip-orphans", action="store_true", help="only build the playlist")
    args = parser.parse_args()

    library = open_library()

    if not args.skip_playlist:
        tidal_ids = load_downloaded_tidal_ids(Path(args.progress))
        print(f"{len(tidal_ids)} tracks marked 'downloaded' in {args.progress}")
        track_ids, missing = add_to_playlist(library, args.playlist_name, tidal_ids)
        print(f"added {len(track_ids)} tracks to playlist '{args.playlist_name}'")
        if missing:
            print(f"{len(missing)} downloaded tidal_ids had no matching row in tracks "
                  f"(check they actually landed in the db): {missing[:10]}{' ...' if len(missing) > 10 else ''}")

    if not args.skip_orphans:
        out_path = Path(args.orphans_out)
        count = report_orphan_tracks(library, out_path)
        print(f"{count} tracks in the library belong to no playlist; written to {out_path}")


if __name__ == "__main__":
    main()
