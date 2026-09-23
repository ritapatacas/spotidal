#!/usr/bin/env python3
"""
Re-derive the correct tidal_id for tracks flagged "suspicious" by
audit_tidal_id_collisions.py (tracks whose tidal_id is shared with an
unrelated track, from the _report_downloads title-substring bug).

For each affected track: read title/artist/isrc/duration straight from its
own local FLAC file (offline, no API), search TIDAL by artist+title text,
and verify candidates with the same match.match() used everywhere else in
the app (ISRC match, or duration+name+artist match). On a confident match
that differs from the current (wrong) tidal_id, updates just that one row
directly by track_id. On no confident match, clears tidal_id to NULL rather
than leave the wrong shared value in place.

This never touches files, never calls download_url()/import_file(), and
never compares against other files in the library — it can't re-trigger
the substring-matching bug that caused the corruption.

Usage:
    poetry run python scripts/fix_tidal_id_collisions.py --dry-run
    poetry run python scripts/fix_tidal_id_collisions.py            # applies fixes
"""
import argparse
import csv
import sqlite3
import time
from pathlib import Path

import tidalapi
from mutagen.flac import FLAC

import spotidal.model.auth as auth
from spotidal.model.helpers.sync import match as _match
from spotidal.model.helpers.type.file import Files

RATE_LIMIT_SLEEP_SECONDS = 30 * 60
SEARCH_DELAY_SECONDS = 1.0

GREY = "\033[38;5;102m"
WHITE = "\033[0m"


def _grey(text):
    return GREY + text + WHITE


def is_rate_limited(error: Exception) -> bool:
    status_code = getattr(getattr(error, "response", None), "status_code", None)
    if status_code == 429:
        return True
    return "429" in str(error) or "too many requests" in str(error).lower()


def read_flac_tags(full_path: Path):
    audio = FLAC(full_path)
    title = (audio.get("title") or [None])[0]
    artist = (audio.get("artist") or [None])[0]
    isrc = (audio.get("isrc") or [None])[0]
    duration = audio.info.length if audio.info else None
    return title, artist, isrc, duration


def build_sp_track(track_id, title, artist, isrc, duration):
    return {
        "id": track_id,
        "name": title,
        "artists": [{"name": artist}],
        "duration_ms": (duration or 0) * 1000,
        "external_ids": {"isrc": isrc} if isrc else {},
    }


def find_tidal_match(td_session, sp_track):
    query = _match.simple(sp_track["name"]) + " " + _match.simple(sp_track["artists"][0]["name"])
    for attempt in range(5):
        try:
            results = td_session.search(query, models=[tidalapi.media.Track])
            break
        except Exception as error:
            if is_rate_limited(error):
                print(_grey(f"  rate limited; sleeping {RATE_LIMIT_SLEEP_SECONDS}s"))
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            raise
    else:
        return None
    for track in results.get("tracks", []):
        if _match.match(track, sp_track):
            return track
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collisions",
        default="/Users/ritapatacas/sound-library/tidal_id_collisions.csv",
    )
    parser.add_argument(
        "--out",
        default="/Users/ritapatacas/sound-library/tidal_id_fixes.csv",
    )
    parser.add_argument("--dry-run", action="store_true", help="search only, do not write to the db")
    parser.add_argument(
        "--apply-from",
        help="skip searching entirely; just apply the fixed/cleared rows from a "
             "previously generated --out csv (e.g. from a --dry-run) to the db",
    )
    args = parser.parse_args()

    settings = Files.SETTINGS.load() or {}
    db_path = settings.get("databaseLocation")
    root = Path(settings.get("flacDirectory", "")).expanduser().parent

    if args.apply_from:
        conn = sqlite3.connect(db_path)
        with open(args.apply_from, newline="", encoding="utf-8") as f:
            fix_rows = list(csv.DictReader(f))
        applied = 0
        for r in fix_rows:
            if r["action"] == "fixed":
                conn.execute(
                    "UPDATE tracks SET tidal_id=?, updated_at=datetime('now') WHERE track_id=?",
                    (r["new_tidal_id"], r["track_id"]),
                )
                applied += 1
            elif r["action"] == "cleared":
                conn.execute(
                    "UPDATE tracks SET tidal_id=NULL, updated_at=datetime('now') WHERE track_id=?",
                    (r["track_id"],),
                )
                applied += 1
        conn.commit()
        print(f"applied {applied} updates from {args.apply_from} to {db_path}")
        return

    with open(args.collisions, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["classification"] == "suspicious"]

    print(f"{len(rows)} suspicious rows to re-check")

    td_session = auth.get_td_session()
    if not td_session:
        raise SystemExit("could not open a TIDAL session")

    conn = sqlite3.connect(db_path)

    fixed = cleared = unchanged = missing_file = 0
    total = len(rows)
    start = time.monotonic()

    with open(args.out, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "action", "track_id", "old_tidal_id", "new_tidal_id",
            "local_duration_s", "new_tidal_duration_s", "duration_diff_s",
            "title", "artist", "flac_path",
        ])

        for i, row in enumerate(rows, 1):
            track_id = row["track_id"]
            old_tidal_id = row["tidal_id"]
            full_path = root / row["flac_path"]

            if not full_path.exists():
                missing_file += 1
                writer.writerow(["missing_file", track_id, old_tidal_id, "", "", "", "", row["title"], row["artist"], row["flac_path"]])
                continue

            title, artist, isrc, duration = read_flac_tags(full_path)
            title = title or row["title"]
            artist = artist or row["artist"]
            sp_track = build_sp_track(track_id, title, artist, isrc, duration)

            time.sleep(SEARCH_DELAY_SECONDS)
            new_track = find_tidal_match(td_session, sp_track)

            new_duration = round(new_track.duration, 1) if new_track and new_track.duration else ""
            local_duration = round(duration, 1) if duration else ""
            duration_diff = round(abs(new_duration - local_duration), 1) if new_duration != "" and local_duration != "" else ""

            if new_track and str(new_track.id) != str(old_tidal_id):
                action = "fixed"
                new_tidal_id = str(new_track.id)
                fixed += 1
                if not args.dry_run:
                    conn.execute("UPDATE tracks SET tidal_id=?, updated_at=datetime('now') WHERE track_id=?", (new_tidal_id, track_id))
                    conn.commit()
            elif new_track:
                action = "unchanged"  # re-found the same id; leave as is
                new_tidal_id = old_tidal_id
                unchanged += 1
            else:
                action = "cleared"
                new_tidal_id = ""
                cleared += 1
                if not args.dry_run:
                    conn.execute("UPDATE tracks SET tidal_id=NULL, updated_at=datetime('now') WHERE track_id=?", (track_id,))
                    conn.commit()

            writer.writerow([
                action, track_id, old_tidal_id, new_tidal_id,
                local_duration, new_duration, duration_diff,
                title, artist, row["flac_path"],
            ])

            elapsed = time.monotonic() - start
            rate = elapsed / i
            body = f" .. checking  -  {100*i/total:3.0f}%  -  {i}/{total} - {total-i} left  -  {rate:.1f}s/t"
            print(_grey(f"{body}  [{action}]"))

    print(f"\ndone: {fixed} fixed, {cleared} cleared (no confident match), "
          f"{unchanged} unchanged, {missing_file} missing files. Details in {args.out}")
    if args.dry_run:
        print("(dry run — nothing was written to the database)")


if __name__ == "__main__":
    main()
