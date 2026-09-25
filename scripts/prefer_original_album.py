#!/usr/bin/env python3
"""
Find tracks in the library currently linked to a compilation/"best of"
album (or a generic algorithmic pseudo-album — TIDAL's catalog is full of
these now: "Trippy Summer", "90er Party Hits", etc., which don't match
any "best of"-style name pattern) and re-point them at the original
studio release when one exists.

For each candidate track:
  1. search TIDAL by title+artist
  2. keep only candidates whose title and artist actually match (not just
     "showed up in the search"), whose album isn't itself compilation-like,
     and whose duration is within DURATION_TOLERANCE_S of the local file's
     real duration (not just ISRC — TIDAL frequently reissues the same
     song under several ISRCs, and restricting to one exact ISRC can rule
     out the one genuine original-album pressing)
  3. of what's left, pick the earliest release_date

Never touches a track with no matching, non-compilation candidate — stays
as-is rather than guessing at something worse. Verified against 7 known
cases before trusting this: see PR discussion / commit message.

Usage:
    poetry run python scripts/prefer_original_album.py --dry-run
    poetry run python scripts/prefer_original_album.py --apply-from PATH  # apply a --dry-run's --out csv
"""
import argparse
import csv
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

import tidalapi
from mutagen.flac import FLAC

import spotidal.model.auth as auth
from spotidal.model.helpers.type.file import Files

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retry_unmatched import split_artists  # noqa: E402

GREY = "\033[38;5;102m"
WHITE = "\033[0m"

DURATION_TOLERANCE_S = 10

COMPILATION_PATTERN = re.compile(
    r"best of|greatest hits|the hits|hits collection|hits of|anthology|"
    r"essential|the very best|collection|compilation|now that.s what|"
    r"top \d|various artists|ultimate.*(hits|collection)|karaoke",
    re.IGNORECASE,
)


def _grey(text):
    return GREY + text + WHITE


def is_compilation(album_name):
    return bool(album_name and COMPILATION_PATTERN.search(album_name))


def strip_diacritics(text):
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in normalized if not unicodedata.combining(c))


def strip_version_suffix(text):
    text = re.sub(r"\s*[-–].*$", "", text or "")
    text = re.sub(r"\s*[\(\[].*$", "", text)
    return text.strip()


def clean(text):
    text = strip_diacritics(strip_version_suffix(text))
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.casefold().split())


def artists_overlap(local_artist, td_track):
    local_set = {clean(a) for a in split_artists(local_artist)}
    td_names = [a.name for a in (td_track.artists or [])] or [td_track.artist.name]
    td_set = {clean(a) for name in td_names for a in split_artists(name)}
    return bool(local_set & td_set)


def local_flac_duration(conn, root, track_id):
    row = conn.execute(
        "SELECT path FROM files WHERE track_id=? AND format='flac' LIMIT 1", (track_id,)
    ).fetchone()
    if not row:
        return None
    try:
        return FLAC(root / row[0]).info.length
    except Exception:
        return None


def find_original_album_track(td_session, title, artist, local_duration):
    query = f"{strip_version_suffix(title)} {artist}"
    results = td_session.search(query, models=[tidalapi.media.Track])
    candidates = []
    for c in results.get("tracks", []):
        if not c.album or is_compilation(c.album.name):
            continue
        if clean(c.name) != clean(title):
            continue
        if not artists_overlap(artist, c):
            continue
        if local_duration and abs(c.duration - local_duration) > DURATION_TOLERANCE_S:
            continue
        candidates.append(c)
    if not candidates:
        return None
    candidates.sort(key=lambda c: c.album.release_date or "9999-99-99")
    return candidates[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/Users/ritapatacas/sound-library/prefer_original_album_report.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply-from", help="apply a previous --out csv's 'fixed' rows without re-searching")
    args = parser.parse_args()

    settings = Files.SETTINGS.load() or {}
    db_path = settings.get("databaseLocation")
    root = Path(settings.get("flacDirectory", "")).expanduser().parent
    conn = sqlite3.connect(db_path)

    if args.apply_from:
        with open(args.apply_from, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["action"] == "fixed"]
        for r in rows:
            conn.execute(
                "UPDATE tracks SET tidal_id=?, album=?, updated_at=datetime('now') WHERE track_id=?",
                (r["new_tidal_id"], r["new_album"], r["track_id"]),
            )
        conn.commit()
        print(f"applied {len(rows)} updates from {args.apply_from}")
        return

    tracks = conn.execute(
        "SELECT track_id, title, artist, album, isrc, tidal_id FROM tracks WHERE album IS NOT NULL"
    ).fetchall()
    candidates = [t for t in tracks if is_compilation(t[3])]
    print(f"{len(tracks)} tracks total, {len(candidates)} currently linked to a compilation-like album")

    td_session = auth.get_td_session()
    if not td_session:
        raise SystemExit("could not open a TIDAL session")

    fixed = kept = errors = 0
    with open(args.out, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "action", "track_id", "title", "artist", "current_album", "current_tidal_id",
            "new_album", "new_tidal_id", "new_release_date",
        ])

        for i, (track_id, title, artist, album, isrc, tidal_id) in enumerate(candidates, 1):
            try:
                local_duration = local_flac_duration(conn, root, track_id)
                time.sleep(1)
                found = find_original_album_track(td_session, title, artist, local_duration)
            except Exception as error:
                errors += 1
                print(_grey(f"  error on {artist} - {title}: {error}"))
                continue

            if found and str(found.id) != str(tidal_id):
                fixed += 1
                writer.writerow([
                    "fixed", track_id, title, artist, album, tidal_id,
                    found.album.name, found.id, found.album.release_date,
                ])
                print(_grey(f"  [{i}/{len(candidates)}] fixed: {artist} - {title} -> {found.album.name}"))
            else:
                kept += 1
                writer.writerow(["kept", track_id, title, artist, album, tidal_id, "", "", ""])

    print(f"\ndone: {fixed} fixed (original album found), {kept} kept (no better option), {errors} errors")
    print(f"details in {args.out}")
    print("(dry run — nothing written to the database; re-run with --apply-from to apply)")


if __name__ == "__main__":
    main()
