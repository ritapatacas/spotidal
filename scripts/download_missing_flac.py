#!/usr/bin/env python3
"""
Search TIDAL for the FLAC of every mp3 in flac_match_report.csv that has
status "NO FLAC", download the matches, and let the existing td_downloader
pipeline import them into the SQLite library.

Usage:
    poetry run python scripts/download_missing_flac.py [--report PATH] [--dry-run]

Resumable: every processed mp3 is appended to a progress CSV next to the
report (download_missing_flac_progress.csv). Re-running the script skips
rows already present there, so it's safe to stop (Ctrl-C) and restart.

On a TIDAL rate limit (HTTP 429 / "too many requests"), the script sleeps
30 minutes and retries the same track rather than giving up on it.
"""
import argparse
import csv
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import mutagen
import tidalapi

import spotidal.model.auth as auth
from spotidal.model.helpers.sync import match as _match
from spotidal.model.helpers.td_downloader import download_url

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
    """Pad `body` with spaces so `tail` lands flush with the terminal's right edge."""
    columns = shutil.get_terminal_size(fallback=(100, 24)).columns
    pad = max(min_pad, columns - len(body) - len(tail))
    return f"{body}{' ' * pad}{tail}"


def is_rate_limited(error: Exception) -> bool:
    status_code = getattr(getattr(error, "response", None), "status_code", None)
    if status_code == 429:
        return True
    return "429" in str(error) or "too many requests" in str(error).lower()


def read_tags(mp3_path: Path):
    """Best-effort ID3 read; falls back to folder/filename when tags are missing."""
    title = artist = album = isrc = None
    duration = None
    try:
        audio = mutagen.File(mp3_path, easy=True)
        if audio is not None:
            title = (audio.get("title") or [None])[0]
            artist = (audio.get("artist") or [None])[0]
            album = (audio.get("album") or [None])[0]
            isrc = (audio.get("isrc") or [None])[0]
            if audio.info is not None:
                duration = audio.info.length
    except Exception:
        pass

    if not title or not artist:
        # sound-library/lib/albums/<artist>/<album>/<NN title>.mp3
        parts = mp3_path.parts
        try:
            lib_index = parts.index("albums")
            fallback_artist = parts[lib_index + 1]
            fallback_album = parts[lib_index + 2]
        except (ValueError, IndexError):
            fallback_artist = mp3_path.parent.parent.name
            fallback_album = mp3_path.parent.name
        stem = mp3_path.stem
        # strip a leading track number ("01 ", "01. ", "01-")
        fallback_title = stem.lstrip("0123456789.- ").strip() or stem
        title = title or fallback_title
        artist = artist or fallback_artist
        album = album or fallback_album

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "isrc": isrc,
        "duration": duration,
    }


def build_sp_track(mp3_path: Path, tags: dict) -> dict:
    sp_track = {
        "id": str(mp3_path),
        "name": tags["title"],
        "artists": [{"name": tags["artist"]}],
        "duration_ms": (tags["duration"] or 0) * 1000,
        "external_ids": {"isrc": tags["isrc"]} if tags["isrc"] else {},
    }
    if tags["album"]:
        sp_track["album"] = {
            "name": tags["album"],
            "artists": [{"name": tags["artist"]}],
        }
    return sp_track


def find_tidal_match(td_session: tidalapi.Session, sp_track: dict):
    query = _match.simple(sp_track["name"]) + " " + _match.simple(sp_track["artists"][0]["name"])
    for attempt in range(5):
        try:
            results = td_session.search(query, models=[tidalapi.media.Track])
            break
        except Exception as error:
            if is_rate_limited(error):
                print(_grey(f"  rate limited during search; sleeping {RATE_LIMIT_SLEEP_SECONDS}s"))
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            raise
    else:
        return None

    for track in results.get("tracks", []):
        if _match.match(track, sp_track):
            return track
    return None


def load_progress(progress_path: Path) -> set:
    if not progress_path.exists():
        return set()
    with open(progress_path, newline="", encoding="utf-8") as f:
        return {row["mp3_path"] for row in csv.DictReader(f)}


def append_progress(progress_path: Path, row: dict, is_new_file: bool):
    with open(progress_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["mp3_path", "result", "tidal_id", "detail"])
        if is_new_file:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default="/Users/ritapatacas/sound-library/flac_match_report.csv",
        help="path to flac_match_report.csv",
    )
    parser.add_argument("--dry-run", action="store_true", help="search only, do not download")
    args = parser.parse_args()

    report_path = Path(args.report)
    progress_path = report_path.parent / "download_missing_flac_progress.csv"
    is_new_progress = not progress_path.exists()

    with open(report_path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "NO FLAC"]

    already_done = load_progress(progress_path)
    pending = [r for r in rows if r["mp3_path"] not in already_done]

    print(f"{len(rows)} tracks marked NO FLAC, {len(already_done)} already processed, "
          f"{len(pending)} left to do")

    td_session = auth.get_td_session()
    if not td_session:
        print("could not open a TIDAL session (run `poetry run spotidal` and log in first)")
        sys.exit(1)

    matched = downloaded = unmatched = failed = 0

    total = len(pending)
    count_width = len(str(total)) if total else 1
    start = time.monotonic()

    def _report_progress(n):
        elapsed = time.monotonic() - start
        left = total - n
        pct = 100 * n / total if total else 100
        rate = elapsed / n if n else 0
        body = (
            f" .. processing  -  {pct:3.0f}%  -  {n:>{count_width}}/{total} "
            f"- {left:>{count_width}} left  -  {rate:.1f}s/t"
        )
        tail = f"[{_format_elapsed(elapsed)}] @ {datetime.now():%H:%M:%S}"
        print(_grey(_right_align(body, tail)))

    for i, row in enumerate(pending, 1):
        mp3_path = Path(row["mp3_path"])
        print(f"[{i}/{total}] {mp3_path.name}")

        if not mp3_path.exists():
            append_progress(
                progress_path,
                {"mp3_path": str(mp3_path), "result": "missing_source", "tidal_id": "", "detail": "mp3 not found on disk"},
                is_new_progress,
            )
            is_new_progress = False
            failed += 1
            _report_progress(i)
            continue

        tags = read_tags(mp3_path)
        sp_track = build_sp_track(mp3_path, tags)

        time.sleep(SEARCH_DELAY_SECONDS)
        track = find_tidal_match(td_session, sp_track)

        if not track:
            print(_grey(f"  no confident TIDAL match for '{tags['artist']} - {tags['title']}'"))
            append_progress(
                progress_path,
                {"mp3_path": str(mp3_path), "result": "unmatched", "tidal_id": "", "detail": f"{tags['artist']} - {tags['title']}"},
                is_new_progress,
            )
            is_new_progress = False
            unmatched += 1
            _report_progress(i)
            continue

        matched += 1
        print(_grey(f"  matched TIDAL track {track.id}: {track.artist.name} - {track.name}"))

        if args.dry_run:
            append_progress(
                progress_path,
                {"mp3_path": str(mp3_path), "result": "matched_dry_run", "tidal_id": str(track.id), "detail": track.name},
                is_new_progress,
            )
            is_new_progress = False
            _report_progress(i)
            continue

        url = f"https://tidal.com/track/{track.id}"
        while True:
            try:
                result = download_url(url, timeout=240)
                break
            except Exception as error:
                if is_rate_limited(error):
                    print(_grey(f"  rate limited during download; sleeping {RATE_LIMIT_SLEEP_SECONDS}s"))
                    time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                    continue
                print(_grey(f"  download failed: {error}"))
                result = None
                break

        if result:
            downloaded += 1
            append_progress(
                progress_path,
                {"mp3_path": str(mp3_path), "result": "downloaded", "tidal_id": str(track.id), "detail": track.name},
                is_new_progress,
            )
        else:
            failed += 1
            append_progress(
                progress_path,
                {"mp3_path": str(mp3_path), "result": "download_failed", "tidal_id": str(track.id), "detail": track.name},
                is_new_progress,
            )
        is_new_progress = False
        _report_progress(i)

    print(
        f"\ndone: {matched} matched ({downloaded} downloaded), "
        f"{unmatched} unmatched, {failed} failed. "
        f"Details in {progress_path}"
    )


if __name__ == "__main__":
    main()
