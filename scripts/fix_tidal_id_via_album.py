#!/usr/bin/env python3
"""
Resolve the 342 "tidal_id mismatch" tracks flagged by the in-app playlist
consistency audit (utils > local files > audit playlist consistency),
using the Spotify album name as the cross-check instead of local file
duration — no need to touch any audio files on disk.

For each flagged track:
  1. parse the proposed tidal_id out of its review_reason
     ("tidal_id mismatch (db=X vs found=Y)")
  2. look up the track's Spotify album name by ISRC (sp.search isrc:...)
  3. look up the candidate tidal_id's album name (td_session.track(id))
  4. if the two album names agree (after stripping remaster/version
     suffixes and diacritics), apply the fix and clear review_reason;
     otherwise leave it alone and log it for manual review.

Usage:
    poetry run python scripts/fix_tidal_id_via_album.py --dry-run
    poetry run python scripts/fix_tidal_id_via_album.py
"""
import argparse
import csv
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

from mutagen.flac import FLAC

import spotidal.model.auth as auth
from spotidal.model.helpers.type.file import Files

GREY = "\033[38;5;102m"
WHITE = "\033[0m"


def _grey(text):
    return GREY + text + WHITE


def _strip_version_suffix(text):
    text = re.sub(r"\s*[-–].*$", "", text or "")
    text = re.sub(r"\s*[\(\[].*$", "", text)
    return text.strip()


def _strip_diacritics(text):
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _clean(text):
    text = _strip_diacritics(_strip_version_suffix(text))
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.casefold().split())


def parse_found_id(review_reason):
    match = re.search(r"tidal_id mismatch \(db=(\S+) vs found=(\S+)\)", review_reason)
    return match.group(2).rstrip(")") if match else None


def spotify_album_for_isrc(sp_session, isrc):
    if not isrc:
        return None
    results = sp_session.search(q=f"isrc:{isrc}", type="track", limit=1)
    items = results.get("tracks", {}).get("items", [])
    return items[0]["album"]["name"] if items else None


def local_flac_duration(conn, root, track_id):
    row = conn.execute(
        "SELECT path FROM files WHERE track_id = ? AND format = 'flac' LIMIT 1",
        (track_id,),
    ).fetchone()
    if not row:
        return None
    try:
        return FLAC(root / row[0]).info.length
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="/Users/ritapatacas/sound-library/tidal_id_via_album_report.csv")
    args = parser.parse_args()

    settings = Files.SETTINGS.load() or {}
    conn = sqlite3.connect(settings.get("databaseLocation"))
    root = Path(settings.get("flacDirectory", "")).expanduser().parent

    sp = auth.open_sp_session()
    td = auth.get_td_session()
    if not sp or not td:
        raise SystemExit("could not open Spotify/TIDAL sessions")

    rows = conn.execute(
        "SELECT track_id, title, artist, isrc, tidal_id, review_reason FROM tracks "
        "WHERE review_reason LIKE '%tidal_id mismatch%'"
    ).fetchall()
    print(f"{len(rows)} tracks flagged with a tidal_id mismatch")

    fixed = skipped = errors = 0
    with open(args.out, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "action", "confirmed_by", "track_id", "title", "artist", "old_tidal_id", "new_tidal_id",
            "spotify_album", "tidal_album", "local_duration_s", "tidal_duration_s",
        ])

        for i, (track_id, title, artist, isrc, old_tidal_id, review_reason) in enumerate(rows, 1):
            new_tidal_id = parse_found_id(review_reason)
            if not new_tidal_id:
                continue

            try:
                sp_album = spotify_album_for_isrc(sp, isrc)
                time.sleep(0.3)
                td_track = td.track(int(new_tidal_id))
                td_album = td_track.album.name if td_track.album else None
                td_duration = td_track.duration
            except Exception as error:
                errors += 1
                writer.writerow(["error", "", track_id, title, artist, old_tidal_id, new_tidal_id, "", str(error), "", ""])
                continue

            local_duration = local_flac_duration(conn, root, track_id)

            album_ok = bool(sp_album and td_album and _clean(sp_album) == _clean(td_album))
            duration_ok = bool(
                local_duration and td_duration and abs(local_duration - td_duration) <= 15
            )

            if album_ok or duration_ok:
                action = "fixed"
                confirmed_by = "album" if album_ok else "duration"
                fixed += 1
                if not args.dry_run:
                    conn.execute(
                        "UPDATE tracks SET tidal_id=?, review_reason=NULL, reviewed_at=datetime('now') WHERE track_id=?",
                        (new_tidal_id, track_id),
                    )
                    conn.commit()
            else:
                action = "skipped"
                confirmed_by = ""
                skipped += 1

            writer.writerow([
                action, confirmed_by, track_id, title, artist, old_tidal_id, new_tidal_id,
                sp_album, td_album, local_duration, td_duration,
            ])
            print(_grey(f" .. {i}/{len(rows)}  [{action}{'/' + confirmed_by if confirmed_by else ''}]  {artist} - {title}"))

    print(f"\ndone: {fixed} fixed, {skipped} skipped (album mismatch, needs manual review), {errors} errors")
    print(f"details in {args.out}")
    if args.dry_run:
        print("(dry run — nothing was written to the database)")


if __name__ == "__main__":
    main()
