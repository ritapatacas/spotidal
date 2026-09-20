import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ..model.library import camelot_related
from .page import PAGE_HTML, SUGGEST_PAGE_HTML


def _float_or_none(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


class _Handler(BaseHTTPRequestHandler):
    library = None  # bound per-server in run_server()

    def log_message(self, format, *args):
        pass  # stay quiet in the terminal while this runs during a set

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
        else:
            self._send_json({"error": "not found"}, status=404)


def run_server(library, host="127.0.0.1", port=8383, open_browser=True):
    """Blocks serving the search UI until Ctrl+C."""
    handler = type("BoundHandler", (_Handler,), {"library": library})
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"search UI running at {url} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
