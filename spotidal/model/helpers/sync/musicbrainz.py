"""
Shared MusicBrainz lookup: given a track's ISRC, find the title of its
genuine original studio album (release-group type "Album", no secondary
type like Compilation/Live/Soundtrack) — used when TIDAL doesn't have (or
match) the album a track is nominally filed under, since that album is
often itself a compilation/pseudo-album rather than the real original
release.

Serializes calls behind MusicBrainz's 1 request/second rate limit with a
plain thread lock, since callers run this from a thread pool (see
sync/search.py's td_search).
"""
import threading
import time

import requests

_HEADERS = {"User-Agent": "spotidal-library-cleanup/1.0 (personal use)"}
_RATE_LIMIT_S = 1.1
_lock = threading.Lock()
_last_call = 0.0


def _get(url, params):
    global _last_call
    with _lock:
        wait = _RATE_LIMIT_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        finally:
            _last_call = time.monotonic()
    response.raise_for_status()
    return response.json()


def original_album_name(isrc):
    if not isrc:
        return None
    try:
        data = _get(f"https://musicbrainz.org/ws/2/isrc/{isrc}", {"fmt": "json"})
    except Exception:
        return None

    recordings = data.get("recordings", [])
    if not recordings:
        return None

    try:
        detail = _get(
            f"https://musicbrainz.org/ws/2/recording/{recordings[0]['id']}",
            {"inc": "releases+release-groups", "fmt": "json"},
        )
    except Exception:
        return None

    studio_releases = [
        r for r in detail.get("releases", [])
        if r.get("release-group", {}).get("primary-type") == "Album"
        and not r.get("release-group", {}).get("secondary-types")
    ]
    if not studio_releases:
        return None
    studio_releases.sort(key=lambda r: r.get("date") or "9999")
    return studio_releases[0]["title"]
