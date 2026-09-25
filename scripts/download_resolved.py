#!/usr/bin/env python3
"""
Download every track chosen in match_ui.py (resolved_matches.csv) that
hasn't been downloaded yet. Adds a downloaded_at column to the same file
so re-running only picks up newly-resolved rows.

Usage:
    poetry run python scripts/download_resolved.py
"""
import csv
import time
from datetime import datetime
from pathlib import Path

from spotidal.model.helpers.td_downloader import download_url

RESOLVED_CSV = Path("/Users/ritapatacas/sound-library/resolved_matches.csv")


def main():
    with open(RESOLVED_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())
    if "downloaded_at" not in fieldnames:
        fieldnames.append("downloaded_at")

    pending = [r for r in rows if not r.get("downloaded_at")]
    print(f"{len(rows)} resolved total, {len(pending)} pending download")

    downloaded = failed = 0
    for i, row in enumerate(pending, 1):
        print(f"[{i}/{len(pending)}] {row['tidal_artist']} - {row['tidal_title']}")
        url = f"https://tidal.com/track/{row['tidal_id']}"
        try:
            result = download_url(url, timeout=240)
        except Exception as error:
            print(f"  failed: {error}")
            result = None
        if result:
            downloaded += 1
            row["downloaded_at"] = datetime.now().isoformat(timespec="seconds")
        else:
            failed += 1
        time.sleep(1)

        with open(RESOLVED_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    print(f"\ndone: {downloaded} downloaded, {failed} failed")


if __name__ == "__main__":
    main()
