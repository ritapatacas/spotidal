#!/usr/bin/env python3
"""
Find every tidal_id in the library that's linked to more than one distinct
FLAC file, and classify each group as "legit" (same song genuinely present
on more than one release/compilation — durations agree) or "suspicious"
(durations disagree enough that it's probably two different songs/versions
incorrectly sharing one tidal_id, from a weak text-only TIDAL match).

Read-only: only reads the db and probes FLAC files for their duration,
never writes anything.

Usage:
    poetry run python scripts/audit_tidal_id_collisions.py [--tolerance 3.0] [--out PATH]
"""
import argparse
import csv
import sqlite3
from pathlib import Path

from mutagen.flac import FLAC

from spotidal.model.helpers.type.file import Files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tolerance", type=float, default=3.0,
                         help="max duration difference (seconds) still considered the same song")
    parser.add_argument("--out", default="/Users/ritapatacas/sound-library/tidal_id_collisions.csv")
    args = parser.parse_args()

    settings = Files.SETTINGS.load() or {}
    db_path = settings.get("databaseLocation")
    root = Path(settings.get("flacDirectory", "")).expanduser().parent

    conn = sqlite3.connect(db_path)
    tidal_ids = [
        row[0] for row in conn.execute(
            "SELECT tidal_id FROM tracks WHERE tidal_id IS NOT NULL "
            "GROUP BY tidal_id HAVING COUNT(DISTINCT track_id) > 1"
        )
    ]
    print(f"{len(tidal_ids)} tidal_ids linked to more than one track_id")

    legit = []
    suspicious = []
    unreadable = []

    for tidal_id in tidal_ids:
        rows = conn.execute(
            "SELECT t.track_id, t.title, t.artist, t.album, f.path "
            "FROM tracks t JOIN files f USING(track_id) "
            "WHERE t.tidal_id = ? AND f.format = 'flac'",
            (tidal_id,),
        ).fetchall()
        by_path = {r[4]: r for r in rows}
        if len(by_path) < 2:
            continue

        entries = []
        for path, row in by_path.items():
            full_path = root / path
            try:
                duration = round(FLAC(full_path).info.length, 1)
            except Exception:
                duration = None
            entries.append({
                "track_id": row[0], "title": row[1], "artist": row[2],
                "album": row[3], "path": path, "duration": duration,
            })

        durations = [e["duration"] for e in entries if e["duration"] is not None]
        if len(durations) < len(entries):
            unreadable.append((tidal_id, entries))
            continue

        spread = max(durations) - min(durations)
        bucket = suspicious if spread > args.tolerance else legit
        bucket.append((tidal_id, entries, spread))

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["classification", "tidal_id", "duration_spread_s", "track_id", "title", "artist", "album", "flac_path"])
        for label, group in (("suspicious", suspicious), ("legit", legit)):
            for tidal_id, entries, spread in group:
                for e in entries:
                    writer.writerow([label, tidal_id, spread, e["track_id"], e["title"], e["artist"], e["album"], e["path"]])
        for tidal_id, entries in unreadable:
            for e in entries:
                writer.writerow(["unreadable", tidal_id, "", e["track_id"], e["title"], e["artist"], e["album"], e["path"]])

    print(f"{len(legit)} legit, {len(suspicious)} suspicious, {len(unreadable)} unreadable (flac missing/corrupt)")
    print(f"full report written to {args.out}")

    print("\n=== suspicious (duration spread > tolerance) ===")
    for tidal_id, entries, spread in sorted(suspicious, key=lambda x: -x[2]):
        print(f"\ntidal_id {tidal_id}  (spread {spread:.1f}s)")
        for e in entries:
            mins, secs = divmod(int(e["duration"]), 60)
            print(f"   [{mins}:{secs:02d}] {e['artist']} - {e['title']}  ({e['album']})")
            print(f"        {e['path']}")


if __name__ == "__main__":
    main()
