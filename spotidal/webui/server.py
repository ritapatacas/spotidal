import csv
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import tidalapi

from ..model.library import camelot_related
from ..view.text import Text as t
from .page import PAGE_HTML, REVIEW_PAGE_HTML, SUGGEST_PAGE_HTML

NOT_FOUND_REVIEW_CSV = Path("~/.config/spotidal/logs/not_found_review.csv").expanduser()
NOT_FOUND_REVIEW_FIELDS = ["playlist", "spotify_id", "title", "artist", "album", "isrc"]

ALBUM_DIFF_REVIEW_CSV = Path("~/.config/spotidal/logs/album_diff_review.csv").expanduser()
ALBUM_DIFF_REVIEW_FIELDS = [
    "playlist", "spotify_id", "title", "artist", "db_album", "spotify_album", "isrc",
]

TIDAL_DIFF_REVIEW_CSV = Path("~/.config/spotidal/logs/tidal_diff_review.csv").expanduser()
TIDAL_DIFF_REVIEW_FIELDS = [
    "playlist", "spotify_id", "title", "artist", "db_tidal_id", "found_tidal_id", "isrc",
]

# name (as used in /api/review/<name>) -> (csv path, fieldnames); "not-found"
# kept as the only tab wired into the review UI's JS beyond flagged/album-diff,
# tidal-diff is exposed here too but has no dedicated tab yet.
REVIEW_CSV_BUCKETS = {
    "not-found": (NOT_FOUND_REVIEW_CSV, NOT_FOUND_REVIEW_FIELDS),
    "album-diff": (ALBUM_DIFF_REVIEW_CSV, ALBUM_DIFF_REVIEW_FIELDS),
    "tidal-diff": (TIDAL_DIFF_REVIEW_CSV, TIDAL_DIFF_REVIEW_FIELDS),
}


def _float_or_none(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _cover_url(track):
    try:
        return track.album.image(160) if track.album else None
    except Exception:
        return None


def _read_bucket_rows(bucket):
    path, _ = REVIEW_CSV_BUCKETS[bucket]
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _dismiss_bucket_row(bucket, spotify_id):
    path, fields = REVIEW_CSV_BUCKETS[bucket]
    rows = [row for row in _read_bucket_rows(bucket) if row.get("spotify_id") != spotify_id]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class _Handler(BaseHTTPRequestHandler):
    library = None  # bound per-server in run_server()
    td_session = None  # bound per-server in run_server()

    def log_message(self, format, *args):
        pass  # stay quiet in the terminal while this runs during a set

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body):
        body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        if parsed.path == "/":
            self._send_html(PAGE_HTML)
        elif parsed.path == "/suggest":
            self._send_html(SUGGEST_PAGE_HTML)
        elif parsed.path == "/api/options":
            self._send_json(self.library.search_filter_options())
        elif parsed.path == "/api/playlist-tree":
            self._send_json(self.library.playlist_tree())
        elif parsed.path == "/api/genre-counts":
            self._send_json(self.library.genre_counts())
        elif parsed.path == "/api/tracks":
            kwargs = dict(
                query=params.get("q") or None,
                artist=params.get("artist") or None,
                title=params.get("title") or None,
                bpm_min=_float_or_none(params.get("bpm_min")),
                bpm_max=_float_or_none(params.get("bpm_max")),
                key=params.get("key") or None,
                genre=params.get("genre") or None,
                style=params.get("style") or None,
                playlist=params.get("playlist") or None,
            )
            limit = _float_or_none(params.get("limit"))
            if limit:
                kwargs["limit"] = int(limit)
            self._send_json(self.library.search_tracks(**kwargs))
        elif parsed.path == "/api/suggest":
            track_id = params.get("track_id")
            if not track_id:
                self._send_json({"error": "track_id required"}, status=400)
                return
            self._send_json(self.library.suggest_tracks(track_id))
        elif parsed.path == "/api/camelot":
            key = (params.get("key") or "").strip().upper()
            self._send_json({"key": key, "related": camelot_related(key)})
        elif parsed.path == "/review":
            self._send_html(REVIEW_PAGE_HTML)
        elif parsed.path == "/api/review/flagged":
            self._send_json(self.library.flagged_tracks())
        elif parsed.path.startswith("/api/review/") and parsed.path.rsplit("/", 1)[-1] in REVIEW_CSV_BUCKETS:
            self._send_json(_read_bucket_rows(parsed.path.rsplit("/", 1)[-1]))
        elif parsed.path == "/api/review/search":
            if self.td_session is None:
                self._send_json({"error": "no TIDAL session available"}, status=400)
                return
            query = params.get("q") or ""
            results = self.td_session.search(query, models=[tidalapi.media.Track])
            candidates = [
                {
                    "id": str(track.id),
                    "artist": track.artist.name if track.artist else None,
                    "name": track.name,
                    "album": track.album.name if track.album else None,
                    "duration": track.duration,
                    "isrc": getattr(track, "isrc", None),
                    "cover": _cover_url(track),
                }
                for track in results.get("tracks", [])[:5]
            ]
            self._send_json(candidates)
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/review/fix":
            data = self._read_json_body()
            track_id = data.get("track_id")
            tidal_id = data.get("tidal_id")
            if not track_id or not tidal_id:
                self._send_json({"error": "track_id and tidal_id required"}, status=400)
                return
            self.library.set_tidal_id(track_id, tidal_id)
            self.library.set_review(track_id, None)
            self._send_json({"ok": True})
        elif parsed.path == "/api/review/dismiss-flagged":
            data = self._read_json_body()
            track_id = data.get("track_id")
            if not track_id:
                self._send_json({"error": "track_id required"}, status=400)
                return
            self.library.set_review(track_id, None)
            self._send_json({"ok": True})
        elif parsed.path.startswith("/api/review/dismiss/") and parsed.path.rsplit("/", 1)[-1] in REVIEW_CSV_BUCKETS:
            bucket = parsed.path.rsplit("/", 1)[-1]
            data = self._read_json_body()
            spotify_id = data.get("spotify_id")
            if not spotify_id:
                self._send_json({"error": "spotify_id required"}, status=400)
                return
            _dismiss_bucket_row(bucket, spotify_id)
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, status=404)


_server = None
_server_url = None


def run_server(library, td_session=None, host="127.0.0.1", port=8383, open_browser=True):
    """Starts the search UI in the background and returns immediately."""
    global _server, _server_url
    url = f"http://{host}:{port}/"
    display_url = f"http://{host}:{port}"
    if _server is not None:
        # Already running from an earlier 'explore library' menu visit; just
        # surface it again instead of trying to bind the port a second time.
        print(t.log(f"UI running at: {display_url}"))
        if open_browser:
            webbrowser.open(_server_url)
        return

    handler = type("BoundHandler", (_Handler,), {"library": library, "td_session": td_session})
    server = ThreadingHTTPServer((host, port), handler)
    _server = server
    _server_url = url
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(t.log(f"UI running at: {display_url}"))
