#!/usr/bin/env python3
"""
Read-only consistency audit: for every track in a given Spotify playlist
(Spotify being the actual source of truth for title/artist/album/isrc),
check it against the local SQLite library — is there a matching local
track (by ISRC), does its title/artist/album agree, does its stored
tidal_id actually resolve to the same song on TIDAL?

This does NOT download anything and NEVER writes to the database — it
only reports. Use it to sanity-check the data before trusting it, e.g.
after the tidal_id corruption bug.

Usage:
    poetry run python scripts/audit_playlist_consistency.py --list
    poetry run python scripts/audit_playlist_consistency.py --playlist "now 2024"
    poetry run python scripts/audit_playlist_consistency.py --playlist "now 2024" --out report.csv
"""
import argparse
import asyncio
import csv
import shutil
import sqlite3
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import tidalapi

import spotidal.model.auth as auth
from spotidal.model.helpers.sync import match as _match
from spotidal.model.helpers.sync.playlists_handler import get_tracks_from_sp_playlist
from spotidal.model.helpers.type.file import Files

RATE_LIMIT_SLEEP_SECONDS = 30 * 60
SEARCH_DELAY_SECONDS = 1.0

GREY = "\033[38;5;102m"
WHITE = "\033[0m"


def _grey(text):
    return GREY + text + WHITE


def _format_elapsed(seconds):
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _right_align(body, tail, min_pad=1):
    columns = shutil.get_terminal_size(fallback=(100, 24)).columns
    pad = max(min_pad, columns - len(body) - len(tail))
    return f"{body}{' ' * pad}{tail}"


def is_rate_limited(error: Exception) -> bool:
    status_code = getattr(getattr(error, "response", None), "status_code", None)
    if status_code == 429:
        return True
    return "429" in str(error) or "too many requests" in str(error).lower()


def _norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    return _match.simple(s).lower().strip()


def list_playlists(sp):
    response = sp.current_user_playlists(limit=50)
    playlists = response["items"]
    while response.get("next"):
        response = sp.next(response)
        playlists.extend(response["items"])
    return playlists


def find_local_track(conn, isrc):
    if not isrc:
        return None
    row = conn.execute(
        "SELECT track_id, title, artist, album, spotify_id, tidal_id FROM tracks WHERE isrc = ?",
        (isrc,),
    ).fetchone()
    if not row:
        return None
    return {
        "track_id": row[0], "title": row[1], "artist": row[2],
        "album": row[3], "spotify_id": row[4], "tidal_id": row[5],
    }


def find_tidal_track(td_session, title, artist, isrc, duration_ms):
    sp_track = {
        "id": isrc or title,
        "name": title,
        "artists": [{"name": artist}],
        "duration_ms": duration_ms or 0,
        "external_ids": {"isrc": isrc} if isrc else {},
    }
    query = _match.simple(title) + " " + _match.simple(artist)
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


async def main_async():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--playlist", help="exact Spotify playlist name to audit")
    parser.add_argument("--list", action="store_true", help="list your Spotify playlists and exit")
    parser.add_argument("--out", default="/Users/ritapatacas/sound-library/playlist_consistency_report.csv")
    parser.add_argument("--skip-tidal-check", action="store_true",
                         help="only check title/artist/album/spotify_id, skip the per-track TIDAL search")
    parser.add_argument(
        "--write-db", action="store_true",
        help="also set tracks.review_reason on a mismatch (and clear it when a "
             "previously-flagged track re-checks clean) — everything else about "
             "this script stays read-only",
    )
    args = parser.parse_args()

    sp = auth.open_sp_session()
    if not sp:
        raise SystemExit("could not open a Spotify session")

    if args.list:
        for p in list_playlists(sp):
            print(f"{p['tracks']['total']:>5} tracks  {p['name']}")
        return

    if not args.playlist:
        raise SystemExit("pass --playlist \"name\" (or --list to see your playlists)")

    playlists = list_playlists(sp)
    sp_playlist = next((p for p in playlists if p["name"] == args.playlist), None)
    if not sp_playlist:
        raise SystemExit(f"no playlist named {args.playlist!r} found in your Spotify account")

    tracks = await get_tracks_from_sp_playlist(sp, sp_playlist)
    print(f"{len(tracks)} tracks in '{args.playlist}'")

    settings = Files.SETTINGS.load() or {}
    conn = sqlite3.connect(settings.get("databaseLocation"))

    td_session = None
    if not args.skip_tidal_check:
        td_session = auth.get_td_session()
        if not td_session:
            raise SystemExit("could not open a TIDAL session (or pass --skip-tidal-check)")

    total = len(tracks)
    start = time.monotonic()

    with open(args.out, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow([
            "playlist", "spotify_id", "sp_title", "sp_artist", "sp_album", "isrc",
            "found_locally", "title_match", "artist_match", "album_match",
            "db_spotify_id", "spotify_id_match",
            "db_tidal_id", "tidal_search_id", "tidal_id_match", "notes",
        ])

        for i, track in enumerate(tracks, 1):
            sp_id = track.get("id")
            title = track.get("name")
            artists = [a["name"] for a in track.get("artists", [])]
            artist = ", ".join(artists)
            album = (track.get("album") or {}).get("name")
            isrc = (track.get("external_ids") or {}).get("isrc")
            duration_ms = track.get("duration_ms")

            local = find_local_track(conn, isrc)
            notes = []

            if not local:
                writer.writerow([
                    args.playlist, sp_id, title, artist, album, isrc,
                    False, "", "", "", "", "", "", "", "", "not found locally (isrc lookup failed)",
                ])
                elapsed = time.monotonic() - start
                body = f" .. auditing  -  {100*i/total:3.0f}%  -  {i}/{total} - {total-i} left"
                tail = f"[{_format_elapsed(elapsed)}] @ {datetime.now():%H:%M:%S}"
                print(_grey(_right_align(body, tail)))
                continue

            title_match = _norm(local["title"]) == _norm(title)
            artist_match = any(_norm(a) in _norm(local["artist"]) or _norm(local["artist"]) in _norm(a) for a in artists) if local["artist"] else False
            album_match = _norm(local["album"]) == _norm(album) if local["album"] and album else None
            spotify_id_match = (local["spotify_id"] == sp_id) if local["spotify_id"] else None
            if not local["spotify_id"]:
                notes.append("db spotify_id empty")

            mismatches = []
            if not title_match:
                mismatches.append(f"title mismatch (db={local['title']!r} vs spotify={title!r})")
            if not artist_match:
                mismatches.append(f"artist mismatch (db={local['artist']!r} vs spotify={artist!r})")
            if album_match is False:
                mismatches.append(f"album mismatch (db={local['album']!r} vs spotify={album!r})")

            tidal_search_id = ""
            tidal_id_match = ""
            if td_session:
                time.sleep(SEARCH_DELAY_SECONDS)
                found = find_tidal_track(td_session, title, artist, isrc, duration_ms)
                if found:
                    tidal_search_id = str(found.id)
                    tidal_id_match = str(found.id) == str(local["tidal_id"]) if local["tidal_id"] else None
                    if not local["tidal_id"]:
                        notes.append("db tidal_id empty")
                    elif not tidal_id_match:
                        mismatches.append(f"tidal_id mismatch (db={local['tidal_id']} vs found={found.id})")
                else:
                    notes.append("no confident tidal match found")

            if args.write_db:
                review_reason = "; ".join(mismatches) if mismatches else None
                conn.execute(
                    "UPDATE tracks SET review_reason=?, reviewed_at=datetime('now') WHERE track_id=?",
                    (review_reason, local["track_id"]),
                )
                conn.commit()

            writer.writerow([
                args.playlist, sp_id, title, artist, album, isrc,
                True, title_match, artist_match, album_match,
                local["spotify_id"], spotify_id_match,
                local["tidal_id"], tidal_search_id, tidal_id_match,
                "; ".join(notes),
            ])

            elapsed = time.monotonic() - start
            body = f" .. auditing  -  {100*i/total:3.0f}%  -  {i}/{total} - {total-i} left"
            tail = f"[{_format_elapsed(elapsed)}] @ {datetime.now():%H:%M:%S}"
            print(_grey(_right_align(body, tail)))

    print(f"\ndone. report written to {args.out}")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
