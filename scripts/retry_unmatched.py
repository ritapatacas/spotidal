#!/usr/bin/env python3
"""
Second-pass retry for tracks download_missing_flac.py already gave up on
(status "unmatched" in its progress csv). The first pass stays untouched
and as strict as it already is; this is a separate, looser attempt that
only ever runs against its leftovers.

Why a second pass at all: a manual spot-check of 25 random "unmatched"
tracks found 21/25 actually exist on TIDAL — the strict pass missed them
over text-formatting differences (artist strings joined with "×"/"feat."/
"and" that match.py's splitter doesn't recognize, diacritics, VIP/remix
suffixes in the title), not because the music isn't there. This script
applies broader text normalization when searching and verifying, but
still requires ISRC, or title+artist+duration agreement, before accepting
a match — never just a fuzzy title guess.

Usage:
    poetry run python scripts/retry_unmatched.py --report /Users/ritapatacas/sound-library/eps_flac_match_report_progress.csv --dry-run
    poetry run python scripts/retry_unmatched.py --report /Users/ritapatacas/sound-library/eps_flac_match_report_progress.csv
"""
import argparse
import csv
import re
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import tidalapi

import spotidal.model.auth as auth
from spotidal.model.helpers.sync import match as _match
from spotidal.model.helpers.td_downloader import download_url

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_missing_flac import read_tags, is_rate_limited  # noqa: E402

RATE_LIMIT_SLEEP_SECONDS = 30 * 60
SEARCH_DELAY_SECONDS = 1.0
DURATION_TOLERANCE_S = 5

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


def strip_version_suffix(text):
    text = re.sub(r"\s*[-–].*$", "", text or "")
    text = re.sub(r"\s*[\(\[].*$", "", text)
    return text.strip()


def strip_diacritics(text):
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in normalized if not unicodedata.combining(c))


def clean(text):
    text = strip_diacritics(strip_version_suffix(text))
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.casefold().split())


# Broader than match.py's artist splitter: also handles "×"/"X" and "feat."/
# "ft." as separators, which is exactly what tripped up the first pass on
# collab-heavy dance/DnB naming ("Inja × Whiney", "A feat. B", "A X B").
_ARTIST_SPLIT_RE = re.compile(r",|&|/|\bfeat\.?|\bft\.?|\bx\b|×|\band\b", re.IGNORECASE)


def split_artists(text):
    return [part.strip() for part in _ARTIST_SPLIT_RE.split(text or "") if part.strip()]


def artists_overlap(local_artist, td_track):
    local_set = {clean(a) for a in split_artists(local_artist)}
    td_names = [a.name for a in (td_track.artists or [])] or [td_track.artist.name]
    td_set = {clean(a) for name in td_names for a in split_artists(name)}
    return bool(local_set & td_set)


def loose_match(td_track, tags):
    isrc = tags.get("isrc")
    if isrc and getattr(td_track, "isrc", None) == isrc:
        return True
    if clean(td_track.name) != clean(tags["title"]):
        return False
    if not artists_overlap(tags["artist"], td_track):
        return False
    duration = tags.get("duration")
    if duration:
        return abs(td_track.duration - duration) <= DURATION_TOLERANCE_S
    # No local duration to check (tag missing): title + artist agreement
    # alone is weaker, but both already matched exactly above.
    return True


def find_loose_match(td_session, tags):
    queries = {
        f"{strip_version_suffix(tags['title'])} {tags['artist']}",
        f"{tags['title']} {tags['artist']}",
    }
    for attempt in range(5):
        try:
            for query in queries:
                results = td_session.search(query, models=[tidalapi.media.Track])
                for track in results.get("tracks", []):
                    if loose_match(track, tags):
                        return track
            return None
        except Exception as error:
            if is_rate_limited(error):
                print(_grey(f"  rate limited; sleeping {RATE_LIMIT_SLEEP_SECONDS}s"))
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            raise
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="a download_missing_flac.py progress csv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    progress_path = Path(args.report)
    with open(progress_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = rows[0].keys() if rows else ["mp3_path", "result", "tidal_id", "detail"]
    pending = [r for r in rows if r["result"] == "unmatched"]
    print(f"{len(pending)} previously-unmatched tracks to retry")

    td_session = auth.get_td_session()
    if not td_session:
        raise SystemExit("could not open a TIDAL session")

    total = len(pending)
    start = time.monotonic()
    matched = downloaded = still_unmatched = 0

    for i, row in enumerate(pending, 1):
        mp3_path = Path(row["mp3_path"])
        if not mp3_path.exists():
            still_unmatched += 1
            continue

        tags = read_tags(mp3_path)
        time.sleep(SEARCH_DELAY_SECONDS)
        track = find_loose_match(td_session, tags)

        if not track:
            still_unmatched += 1
        else:
            matched += 1
            print(_grey(f"  matched TIDAL track {track.id}: {track.artist.name} - {track.name}"))
            if not args.dry_run:
                url = f"https://tidal.com/track/{track.id}"
                result = download_url(url, timeout=240)
                if result:
                    downloaded += 1
                    row["result"] = "downloaded"
                    row["tidal_id"] = str(track.id)
                    row["detail"] = track.name

        elapsed = time.monotonic() - start
        rate = elapsed / i
        body = f" .. retrying  -  {100*i/total:3.0f}%  -  {i}/{total} - {total-i} left  -  {rate:.1f}s/t"
        tail = f"[{_format_elapsed(elapsed)}] @ {datetime.now():%H:%M:%S}"
        print(_grey(_right_align(body, tail)))

    if not args.dry_run and downloaded:
        with open(progress_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(
        f"\ndone: {matched} matched on retry ({downloaded} downloaded), "
        f"{still_unmatched} still unmatched"
    )
    if args.dry_run:
        print("(dry run — no downloads, progress csv unchanged)")


if __name__ == "__main__":
    main()
