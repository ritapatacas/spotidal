#!/usr/bin/env python3
"""
Find tracks in the library currently linked to a "best of"/compilation
album (or a generic algorithmic pseudo-album TIDAL's catalog is now full
of — "Trippy Summer", "90er Party Hits", etc. — that don't match any
"best of"-style name pattern) and re-point them at the real original
studio album, using MusicBrainz as an independent arbiter instead of
guessing from name patterns or "earliest date on TIDAL" (both proved
unreliable — TIDAL is full of unlabeled compilations).

For each candidate track:
  1. look up its ISRC on MusicBrainz (musicbrainz.org/ws/2/isrc/<isrc>)
  2. fetch that recording's releases, filtered to release-group
     primary-type "Album" with no secondary-types (no Compilation/Live/
     Soundtrack/Remix/etc tag) — the genuine studio album(s)
  3. take the earliest such release's title as the canonical original
     album name
  4. search TIDAL for title+artist, and accept a candidate only if its
     title/artist/duration match AND its album name matches (loosely)
     the MusicBrainz-confirmed original album name

Skips (leaves untouched) whenever MusicBrainz has no ISRC match, no
clean "Album"-type release, or TIDAL doesn't have that specific album —
never guesses a fix without independent confirmation.

Respects MusicBrainz's 1 request/second rate limit.

Usage:
    poetry run python scripts/prefer_original_album.py --dry-run
    poetry run python scripts/prefer_original_album.py --apply-from PATH
"""
import argparse
import csv
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

import requests
import tidalapi

import spotidal.model.auth as auth
from spotidal.model.helpers.type.file import Files

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retry_unmatched import split_artists  # noqa: E402

GREY = "\033[38;5;102m"
WHITE = "\033[0m"

DURATION_TOLERANCE_S = 10
MB_HEADERS = {"User-Agent": "spotidal-library-cleanup/1.0 (personal use)"}
MB_RATE_LIMIT_S = 1.1

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


_last_mb_call = 0.0


def _mb_get(url, params):
    global _last_mb_call
    wait = MB_RATE_LIMIT_S - (time.monotonic() - _last_mb_call)
    if wait > 0:
        time.sleep(wait)
    response = requests.get(url, params=params, headers=MB_HEADERS, timeout=15)
    _last_mb_call = time.monotonic()
    response.raise_for_status()
    return response.json()


def musicbrainz_original_album(isrc):
    if not isrc:
        return None
    try:
        data = _mb_get(f"https://musicbrainz.org/ws/2/isrc/{isrc}", {"fmt": "json"})
    except requests.exceptions.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            return None
        raise
    recordings = data.get("recordings", [])
    if not recordings:
        return None
    recording_id = recordings[0]["id"]
    detail = _mb_get(
        f"https://musicbrainz.org/ws/2/recording/{recording_id}",
        {"inc": "releases+release-groups", "fmt": "json"},
    )
    studio_releases = [
        r for r in detail.get("releases", [])
        if r.get("release-group", {}).get("primary-type") == "Album"
        and not r.get("release-group", {}).get("secondary-types")
    ]
    if not studio_releases:
        return None
    studio_releases.sort(key=lambda r: r.get("date") or "9999")
    return studio_releases[0]["title"]


def find_tidal_track_in_album(td_session, title, artist, album_name, local_duration):
    query = f"{strip_version_suffix(title)} {artist}"
    results = td_session.search(query, models=[tidalapi.media.Track])
    for c in results.get("tracks", []):
        if not c.album or clean(c.album.name) != clean(album_name):
            continue
        if clean(c.name) != clean(title):
            continue
        if not artists_overlap(artist, c):
            continue
        if local_duration and abs(c.duration - local_duration) > DURATION_TOLERANCE_S:
            continue
        return c
    return None


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
            "mb_original_album", "new_tidal_id", "new_album",
        ])

        for i, (track_id, title, artist, album, isrc, tidal_id) in enumerate(candidates, 1):
            try:
                original_album = musicbrainz_original_album(isrc)
            except Exception as error:
                errors += 1
                print(_grey(f"  musicbrainz error on {artist} - {title}: {error}"))
                writer.writerow(["error", track_id, title, artist, album, tidal_id, "", "", ""])
                continue

            if not original_album or clean(original_album) == clean(album):
                kept += 1
                writer.writerow(["kept", track_id, title, artist, album, tidal_id, original_album or "", "", ""])
                print(_grey(f"  [{i}/{len(candidates)}] kept: {artist} - {title}"))
                continue

            root_row = None
            try:
                from mutagen.flac import FLAC
                row = conn.execute(
                    "SELECT path FROM files WHERE track_id=? AND format='flac' LIMIT 1", (track_id,)
                ).fetchone()
                local_duration = FLAC(root / row[0]).info.length if row else None
                time.sleep(1)
                found = find_tidal_track_in_album(td_session, title, artist, original_album, local_duration)
            except Exception as error:
                errors += 1
                print(_grey(f"  tidal error on {artist} - {title}: {error}"))
                writer.writerow(["error", track_id, title, artist, album, tidal_id, original_album, "", ""])
                continue

            if found and str(found.id) != str(tidal_id):
                fixed += 1
                writer.writerow([
                    "fixed", track_id, title, artist, album, tidal_id,
                    original_album, found.id, found.album.name,
                ])
                print(_grey(f"  [{i}/{len(candidates)}] fixed: {artist} - {title} -> {found.album.name}"))
            else:
                kept += 1
                writer.writerow(["kept", track_id, title, artist, album, tidal_id, original_album, "", ""])

    print(f"\ndone: {fixed} fixed, {kept} kept, {errors} errors")
    print(f"details in {args.out}")
    print("(dry run — nothing written to the database; re-run with --apply-from to apply)")


if __name__ == "__main__":
    main()
