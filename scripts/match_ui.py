#!/usr/bin/env python3
"""
Tiny local web UI to manually resolve the "404" tracks (spotidal_404_tracks.csv)
against TIDAL: pick a row, see the top 5 TIDAL search results, click one to
save it. Doesn't download anything — just records the chosen tidal_id so a
separate download step can use it later.

Usage:
    poetry run python scripts/match_ui.py
    (then open http://127.0.0.1:8484)
"""
import csv
import json
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import tidalapi

import spotidal.model.auth as auth

SOUND_LIBRARY = Path("/Users/ritapatacas/sound-library")
SOURCE_CSV = SOUND_LIBRARY / "spotidal_404_tracks.csv"
RESOLVED_CSV = SOUND_LIBRARY / "resolved_matches.csv"
RESOLVED_FIELDS = [
    "playlist", "artist", "title", "album", "spotify_id",
    "tidal_id", "tidal_artist", "tidal_title", "tidal_album", "resolved_at",
]

PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>match ui</title>
<style>
  body { font-family: -apple-system, sans-serif; margin: 0; display: flex; height: 100vh; }
  #left { flex: 1.3; overflow-y: auto; border-right: 1px solid #ddd; }
  #right { flex: 1; padding: 16px; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; }
  tr { cursor: pointer; }
  tr:hover { background: #f5f5f5; }
  tr.resolved { color: #999; }
  tr.selected { background: #dbeafe; }
  .candidate { border: 1px solid #ddd; border-radius: 6px; padding: 10px; margin-bottom: 8px; cursor: pointer; display: flex; align-items: center; }
  .candidate:hover { background: #f0f9ff; }
  .candidate.picked { background: #d1fae5; border-color: #10b981; }
  h3 { margin-top: 0; }
  .muted { color: #888; font-size: 12px; }
  #status { padding: 8px 16px; font-size: 13px; color: #555; }
</style>
</head>
<body>
<div id="left">
  <div id="status">a carregar...</div>
  <table id="rows"><thead><tr><th>playlist</th><th>artista</th><th>titulo</th><th>album</th></tr></thead><tbody></tbody></table>
</div>
<div id="right"><p class="muted">clica numa linha para pesquisar no TIDAL</p></div>

<script>
let rows = [];
let currentIndex = null;

async function loadRows() {
  const res = await fetch('/api/rows');
  rows = await res.json();
  render();
}

function render() {
  const tbody = document.querySelector('#rows tbody');
  tbody.innerHTML = '';
  const resolvedCount = rows.filter(r => r.resolved).length;
  document.getElementById('status').textContent = `${rows.length} tracks - ${resolvedCount} resolvidas`;
  rows.forEach((r, i) => {
    const tr = document.createElement('tr');
    tr.className = (r.resolved ? 'resolved' : '') + (i === currentIndex ? ' selected' : '');
    tr.innerHTML = `<td>${r.playlist}</td><td>${r.artist}</td><td>${r.title}</td><td>${r.album || ''}</td>`;
    tr.onclick = () => selectRow(i);
    tbody.appendChild(tr);
  });
}

function selectRow(i) {
  currentIndex = i;
  render();
  const row = rows[i];
  runSearch(i, `${row.title} ${row.artist}`);
}

async function runSearch(i, query) {
  const right = document.getElementById('right');
  const row = rows[i];
  right.innerHTML = `
    <h3>${row.artist} - ${row.title}</h3>
    <p class="muted">${row.album || ''}</p>
    <div id="searchbox">
      <input id="q" type="text" value="${query.replace(/"/g, '&quot;')}" style="width:70%">
      <button id="go">pesquisar</button>
    </div>
    <div id="candidates"><p class="muted">a pesquisar...</p></div>
  `;
  document.getElementById('go').onclick = () => runSearch(i, document.getElementById('q').value);
  document.getElementById('q').onkeydown = (e) => { if (e.key === 'Enter') runSearch(i, e.target.value); };

  const res = await fetch('/api/search?index=' + i + '&q=' + encodeURIComponent(query));
  const candidates = await res.json();
  const box = document.getElementById('candidates');
  box.innerHTML = '';
  if (!candidates.length) {
    box.innerHTML = '<p class="muted">sem resultados no TIDAL</p>';
    return;
  }
  candidates.forEach(c => {
    const div = document.createElement('div');
    div.className = 'candidate';
    const mins = Math.floor(c.duration / 60);
    const secs = String(c.duration % 60).padStart(2, '0');
    const cover = c.cover
      ? `<img src="${c.cover}" width="56" height="56" style="border-radius:4px;margin-right:10px;vertical-align:middle">`
      : `<div style="width:56px;height:56px;background:#eee;border-radius:4px;display:inline-block;margin-right:10px;vertical-align:middle"></div>`;
    div.innerHTML = `${cover}<span style="vertical-align:middle"><b>${c.artist}</b> - ${c.name}<br><span class="muted">${c.album || ''} [${mins}:${secs}]</span></span>`;
    div.onclick = () => pick(i, c, div);
    box.appendChild(div);
  });
}

async function pick(i, candidate, el) {
  document.querySelectorAll('.candidate').forEach(x => x.classList.remove('picked'));
  el.classList.add('picked');
  await fetch('/api/select', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({index: i, candidate: candidate}),
  });
  rows[i].resolved = true;
  render();
}

loadRows();
</script>
</body>
</html>
"""


def _cover_url(track):
    try:
        return track.album.image(160) if track.album else None
    except Exception:
        return None


def load_source_rows():
    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_resolved_spotify_ids():
    if not RESOLVED_CSV.exists():
        return set()
    with open(RESOLVED_CSV, newline="", encoding="utf-8") as f:
        return {row["spotify_id"] for row in csv.DictReader(f)}


def append_resolved(row, candidate):
    is_new = not RESOLVED_CSV.exists()
    with open(RESOLVED_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESOLVED_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "playlist": row["playlist"],
            "artist": row["artist"],
            "title": row["title"],
            "album": row["album"],
            "spotify_id": row["spotify_id"],
            "tidal_id": candidate["id"],
            "tidal_artist": candidate["artist"],
            "tidal_title": candidate["name"],
            "tidal_album": candidate["album"],
            "resolved_at": datetime.now().isoformat(timespec="seconds"),
        })


class Handler(BaseHTTPRequestHandler):
    source_rows = []
    td_session = None

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/rows":
            resolved_ids = load_resolved_spotify_ids()
            payload = [
                {**r, "resolved": r["spotify_id"] in resolved_ids}
                for r in self.source_rows
            ]
            self._send_json(payload)
        elif parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            index = int(params["index"][0])
            row = self.source_rows[index]
            query = params.get("q", [f"{row['title']} {row['artist']}"])[0]
            results = self.td_session.search(query, models=[tidalapi.media.Track])
            candidates = [
                {
                    "id": t.id,
                    "artist": t.artist.name,
                    "name": t.name,
                    "album": t.album.name if t.album else None,
                    "duration": t.duration,
                    "cover": _cover_url(t),
                }
                for t in results.get("tracks", [])[:5]
            ]
            self._send_json(candidates)
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/select":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            row = self.source_rows[data["index"]]
            append_resolved(row, data["candidate"])
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, status=404)

    def log_message(self, format, *args):
        pass  # keep the terminal quiet


def main():
    Handler.source_rows = load_source_rows()
    print(f"{len(Handler.source_rows)} tracks loaded from {SOURCE_CSV}")

    Handler.td_session = auth.get_td_session()
    if not Handler.td_session:
        raise SystemExit("could not open a TIDAL session")

    server = ThreadingHTTPServer(("127.0.0.1", 8484), Handler)
    url = "http://127.0.0.1:8484"
    print(f"serving at {url}  (resolved matches saved to {RESOLVED_CSV})")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
