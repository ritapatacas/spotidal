#!/usr/bin/env python3
"""
Build a flac_match_report.csv-shaped report for a source folder that (unlike
sound-library/lib/albums) isn't mirrored 1:1 against the flac tree's
Artist/Album layout — e.g. compilations (flat "Compilation Name/track.mp3")
or EPs-et-al (Artist/EP name/track.mp3, which *is* mirrored, but is handled
the same way here for simplicity).

Instead of comparing folder structures, this checks the already-indexed
SQLite library: a track counts as MATCHED if it (or an ISRC/title+artist
match of it) already has a FLAC file on disk; otherwise NO FLAC.

Usage:
    poetry run python scripts/scan_missing_flac.py --source-dir "/Users/ritapatacas/sound-library/lib/compilations" --out /Users/ritapatacas/sound-library/compilations_flac_match_report.csv
"""
import argparse
import csv
import sqlite3
from pathlib import Path

import mutagen

from spotidal.model.helpers.sync import match as _match
from spotidal.model.helpers.type.file import Files


def read_tags(mp3_path: Path):
    title = artist = isrc = None
    try:
        audio = mutagen.File(mp3_path, easy=True)
        if audio is not None:
            title = (audio.get("title") or [None])[0]
            artist = (audio.get("artist") or [None])[0]
            isrc = (audio.get("isrc") or [None])[0]
    except Exception:
        pass
    if not title:
        title = mp3_path.stem.lstrip("0123456789.,- ").strip() or mp3_path.stem
    if not artist:
        artist = mp3_path.parent.name
    return title, artist, isrc


VERSION_KEYWORDS = (
    "remix", "extended", "live", "acoustic", "instrumental", "acapella",
    "radio edit", "vip", "dub", "rework", "flip", "bootleg",
)


def _version_mismatch(title_a: str, title_b: str) -> bool:
    a, b = title_a.lower(), title_b.lower()
    return any((kw in a) != (kw in b) for kw in VERSION_KEYWORDS)


def find_existing_flac(connection, title, artist, isrc, filename_hint=""):
    if isrc:
        row = connection.execute(
            "SELECT f.path FROM tracks t JOIN files f USING(track_id) "
            "WHERE t.isrc = ? AND f.format = 'flac' LIMIT 1",
            (isrc,),
        ).fetchone()
        if row:
            return row[0]

    simple_title = _match.simple(title).lower().strip()
    simple_artist = _match.simple(artist).lower().strip()
    if not simple_title:
        return None

    candidates = connection.execute(
        "SELECT f.path, t.title, t.artist FROM tracks t JOIN files f USING(track_id) "
        "WHERE f.format = 'flac' AND t.title LIKE ?",
        (f"%{simple_title.split()[0]}%",) if simple_title else ("%",),
    ).fetchall()

    for path, db_title, db_artist in candidates:
        if _match.simple(db_title).lower().strip() != simple_title:
            continue
        if simple_artist and simple_artist not in _match.simple(db_artist).lower():
            continue
        flac_filename = path.rsplit("/", 1)[-1]
        if _version_mismatch(filename_hint or title, flac_filename):
            continue
        return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    settings = Files.SETTINGS.load() or {}
    db_path = settings.get("databaseLocation")
    if not db_path or not Path(db_path).exists():
        raise SystemExit(f"database not found at {db_path!r} — is /Volumes/pen mounted?")

    mp3_files = sorted(Path(args.source_dir).rglob("*.mp3"))
    print(f"{len(mp3_files)} mp3 files found under {args.source_dir}")

    connection = sqlite3.connect(db_path)
    matched = 0
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["status", "mp3_path", "flac_path"])
        for mp3_path in mp3_files:
            title, artist, isrc = read_tags(mp3_path)
            flac_path = find_existing_flac(connection, title, artist, isrc, filename_hint=mp3_path.stem)
            if flac_path:
                matched += 1
                writer.writerow(["MATCHED", str(mp3_path), flac_path])
            else:
                writer.writerow(["NO FLAC", str(mp3_path), ""])
    connection.close()

    print(f"{matched} already have a flac, {len(mp3_files) - matched} do not. "
          f"Report written to {args.out}")


if __name__ == "__main__":
    main()
