import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TCON

from .helpers.type.file import Files
from ..view.text import Text as t


CACHE_PATH = Path("~/.config/spotidal/discogs_cache.json").expanduser()
MB_UA = "spotidal/1.0 ( genre-backfill ; mailto:spotidal@example.com )"
DISCOGS_UA = "spotidal/1.0 ( genre-backfill )"

# Discogs' 757 styles are too granular for a DJ crate; fold them into stable
# buckets. Lookup order: exact style, substring rules, then genre fallback.
STYLE_TO_BUCKET = {
    "tech house": "Tech House",
    "house": "House", "deep house": "House", "acid house": "House",
    "hip-house": "House", "hip house": "House", "ghetto house": "House",
    "tribal house": "House", "hard house": "House", "future house": "House",
    "garage house": "House", "jackin house": "House",
    "techno": "Techno", "minimal techno": "Techno", "dub techno": "Techno",
    "hard techno": "Techno", "deep techno": "Techno", "bouncy techno": "Techno",
    "microhouse": "Techno", "freetekno": "Techno", "schranz": "Techno",
    "acid": "Techno", "detroit": "Techno",
    "progressive house": "Melodic House", "balearic": "Melodic House",
    "trance": "Trance", "hard trance": "Trance", "euro trance": "Trance",
    "tech trance": "Trance", "neo trance": "Trance",
    "uplifting trance": "Trance", "psy-trance": "Psy & Goa",
    "goa trance": "Psy & Goa", "suomisaundi": "Psy & Goa", "nightpsy": "Psy & Goa",
    "electro": "Electro & EBM", "electro house": "Electro & EBM",
    "electroclash": "Electro & EBM", "ebm": "Electro & EBM",
    "rhythmic noise": "Electro & EBM", "dark electro": "Electro & EBM",
    "industrial": "Electro & EBM", "new beat": "Electro & EBM",
    "synthwave": "Synthwave & Retro-Electro", "berlin-school": "Synthwave & Retro-Electro",
    "bitpop": "Synthwave & Retro-Electro", "chiptune": "Synthwave & Retro-Electro",
    "vaporwave": "Synthwave & Retro-Electro", "future funk": "Synthwave & Retro-Electro",
    "drum n bass": "Drum & Bass", "drum and bass": "Drum & Bass",
    "jungle": "Drum & Bass", "breakcore": "Drum & Bass", "break-in": "Drum & Bass",
    "uk garage": "UK Garage", "speed garage": "UK Garage", "2-step": "UK Garage",
    "2-step garage": "UK Garage", "uk funky": "UK Garage",
    "breakbeat": "Bass & Breaks", "broken beat": "Bass & Breaks",
    "skweee": "Bass & Breaks", "halftime": "Bass & Breaks",
    "bass music": "Bass & Breaks", "moombahton": "Bass & Breaks",
    "bassline": "Bass & Breaks", "footwork": "Bass & Breaks",
    "phonk": "Bass & Breaks", "ghettotech": "Bass & Breaks", "trap": "Bass & Breaks",
    "future bass": "Bass & Breaks", "baltimore club": "Bass & Breaks",
    "jersey club": "Bass & Breaks", "gqom": "Bass & Breaks", "singeli": "Bass & Breaks",
    "witch house": "Bass & Breaks", "donk": "Bass & Breaks", "bounce": "Bass & Breaks",
    "funkot": "Bass & Breaks", "happy hardcore": "Hardcore", "hardcore": "Hardcore",
    "gabber": "Hardcore", "power violence": "Hardcore", "speedcore": "Hardcore",
    "macina": "Hardcore", "makina": "Hardcore", "jumpstyle": "Hardcore",
    "hands up": "Hardcore", "hi nrg": "Hardcore",
    "disco": "Disco & Nu-Disco", "nu-disco": "Disco & Nu-Disco",
    "euro-disco": "Disco & Nu-Disco", "italo-disco": "Disco & Nu-Disco",
    "italodance": "Disco & Nu-Disco", "boogie": "Funk & Boogie",
    "p.funk": "Funk & Boogie", "g-funk": "Funk & Boogie", "bayou funk": "Funk & Boogie",
    "go-go": "Funk & Boogie", "funk": "Funk & Boogie", "soul": "Funk & Boogie",
    "neo soul": "Funk & Boogie", "uk street soul": "Funk & Boogie",
    "funk metal": "Rock", "jazz-funk": "Jazz", "free funk": "Jazz",
    "downtempo": "Downtempo & Trip-Hop", "trip hop": "Downtempo & Trip-Hop",
    "illbient": "Downtempo & Trip-Hop", "ambient": "Downtempo & Trip-Hop",
    "dark ambient": "Downtempo & Trip-Hop", "chillwave": "Downtempo & Trip-Hop",
    "new age": "Downtempo & Trip-Hop", "idm": "Downtempo & Trip-Hop",
    "hip hop": "Hip-Hop", "boom bap": "Hip-Hop", "conscious": "Hip-Hop",
    "gangsta": "Hip-Hop", "crunk": "Hip-Hop", "cloud rap": "Hip-Hop",
    "memphis rap": "Hip-Hop", "thug rap": "Hip-Hop", "pop rap": "Hip-Hop",
    "hardcore hip-hop": "Hip-Hop", "rnB/swing": "Hip-Hop", "new jack swing": "Hip-Hop",
    "contemporary r&b": "Hip-Hop", "hyphy": "Hip-Hop", "nerdcore techno": "Hip-Hop",
    "low bap": "Hip-Hop", "rap": "Hip-Hop",
    "jazz": "Jazz", "bop": "Jazz", "hard bop": "Jazz", "post bop": "Jazz",
    "cool jazz": "Jazz", "free jazz": "Jazz", "big band": "Jazz",
    "spiritual jazz": "Jazz", "avant-garde jazz": "Jazz", "nu jazz": "Jazz",
    "soul-jazz": "Jazz", "gypsy jazz": "Jazz", "dixieland": "Jazz",
    "smooth jazz": "Jazz", "modal": "Jazz", "third stream": "Jazz",
}
GENRE_TO_BUCKET = {
    "electronic": "Electronic / Other", "hip hop": "Hip-Hop",
    "hip-hop": "Hip-Hop", "rock": "Rock", "pop": "Pop", "jazz": "Jazz",
    "funk / soul": "Funk & Boogie", "latin": "Latin", "reggae": "Reggae & Dub",
    "blues": "Blues", "folk, world, & country": "Folk & World",
    "stage & screen": "Soundtrack", "classical": "Classical",
    "non-music": "Spoken / Other", "children's": "Spoken / Other",
    "brass & military": "Spoken / Other", "easy listening": "Downtempo & Trip-Hop",
}
# Applied to the raw style string after the exact table misses.
SUBSTRING_RULES = [
    ("disco polo", "Latin"),
    ("tropical house", "House"),
    ("house", "House"),
    ("techno", "Techno"),
    ("trance", "Trance"),
    ("dub", "Reggae & Dub"),
    ("reggae", "Reggae & Dub"),
    ("ska", "Reggae & Dub"),
    ("disco", "Disco & Nu-Disco"),
    ("funk", "Funk & Boogie"),
    ("soul", "Funk & Boogie"),
    ("r&b", "Hip-Hop"),
    ("rap", "Hip-Hop"),
    ("hip-hop", "Hip-Hop"),
    ("bass", "Bass & Breaks"),
    ("garage", "UK Garage"),
    ("break", "Bass & Breaks"),
    ("jazz", "Jazz"),
    ("salsa", "Latin"), ("samba", "Latin"), ("bossa", "Latin"),
    ("merengue", "Latin"), ("cumbia", "Latin"), ("tango", "Latin"),
    ("reggaeton", "Latin"), ("mpb", "Latin"), ("latin", "Latin"), ("afro", "Afro"),
    ("punk", "Rock"), ("metal", "Rock"), ("grunge", "Rock"),
    ("synth-pop", "Pop"), ("pop", "Pop"),
    ("world", "Folk & World"), ("folk", "Folk & World"),
    ("opera", "Classical"), ("orchestra", "Classical"), ("choral", "Classical"),
    ("soundtrack", "Soundtrack"), ("score", "Soundtrack"),
]


def bucket_for(genres, styles):
    for style in styles or []:
        key = (style or "").strip().casefold()
        if key in STYLE_TO_BUCKET:
            return STYLE_TO_BUCKET[key]
    for style in styles or []:
        key = unicodedata.normalize("NFC", (style or "").casefold())
        for needle, bucket in SUBSTRING_RULES:
            if needle in key:
                return bucket
    for genre in genres or []:
        bucket = GENRE_TO_BUCKET.get((genre or "").strip().casefold())
        if bucket:
            return bucket
    return None


def _norm(text):
    text = re.sub(r"[^\w]+", " ", text or "")
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


_TRAILING_PARENTHESIS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$")


def clean_query(text):
    # "(Radio Edit)", "(Original Mix)", "(Remix)"... break Discogs'
    # release_title matching, so retry searches with them stripped.
    text = (text or "").strip()
    while True:
        stripped = _TRAILING_PARENTHESIS.sub("", text).strip()
        if stripped == text:
            return text
        text = stripped


class DiscogsClient:
    DISCOGS_INTERVAL = 2.6
    DISCOGS_INTERVAL_AUTH = 1.2
    MB_INTERVAL = 1.1

    def __init__(self, report):
        self._report = report
        credentials = Files.CREDENTIALS.load() or {}
        self._token = ((credentials.get("discogs") or {}).get("token") or "").strip()
        self._intervals = {
            "discogs": self.DISCOGS_INTERVAL_AUTH if self._token else self.DISCOGS_INTERVAL,
            "musicbrainz": self.MB_INTERVAL,
        }
        self._last = {"discogs": 0.0, "musicbrainz": 0.0}
        self._locks = {"discogs": threading.Lock(), "musicbrainz": threading.Lock()}
        self._cache = self._load_cache()
        self._cache_lock = threading.Lock()
        self._calls = 0
        self._calls_lock = threading.Lock()

    @property
    def calls(self):
        with self._calls_lock:
            return self._calls

    @calls.setter
    def calls(self, value):
        with self._calls_lock:
            self._calls = value

    @property
    def authenticated(self):
        return bool(self._token)

    def _load_cache(self):
        try:
            return json.loads(CACHE_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self):
        with self._cache_lock:
            snapshot = json.dumps(self._cache, indent=1)
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(snapshot, encoding="utf-8")
        except OSError as error:
            self._report.warn(f"unable to save cache: {error}")

    @staticmethod
    def _host(url):
        return "musicbrainz" if "musicbrainz.org" in url else "discogs"

    def _throttle(self, host):
        # Sleeps inside the per-host lock: callers are paced one-per-interval
        # per host, so Discogs and MusicBrainz traffic still overlaps freely.
        lock = self._locks[host]
        with lock:
            wait = self._intervals[host] - (time.monotonic() - self._last[host])
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()

    def _get(self, url, headers):
        self._throttle(self._host(url))
        with self._calls_lock:
            self._calls += 1
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=20) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code in (429, 503) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                if error.code == 404:
                    return None
                raise
            except urllib.error.URLError:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        return None

    def _discogs_headers(self):
        headers = {"User-Agent": DISCOGS_UA, "Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Discogs token={self._token}"
        return headers

    def cached(self, key):
        with self._cache_lock:
            return self._cache.get(key)

    def store(self, key, value):
        with self._cache_lock:
            self._cache[key] = value

    def _parse_results(self, results, target, artist, strict):
        matches = []
        for item in results[:10]:
            parts = re.split(r"\s+[\u2013\u2014-]\s+", item.get("title", ""), maxsplit=1)
            rel_title = parts[-1] if len(parts) > 1 else item.get("title", "")
            rel_artists = parts[0] if len(parts) > 1 else ""
            exact = target is not None and _norm(rel_title) == target and (
                not rel_artists or _norm(artist) in _norm(rel_artists)
            )
            if exact or not strict:
                matches.append({
                    "id": item["id"],
                    "title": item.get("title", ""),
                    "year": item.get("year") or "",
                    "master_id": item.get("master_id"),
                    "label": (item.get("label") or [None])[0],
                    "catalog_number": item.get("catno") or None,
                    "genres": item.get("genre") or [],
                    "styles": item.get("style") or [],
                    "exact": exact,
                })
        return matches

    def search_release(self, album, artist, strict=True):
        query = urllib.parse.urlencode(
            {"release_title": album, "artist": artist, "type": "release"}
        )
        data = self._get(
            "https://api.discogs.com/database/search?" + query, self._discogs_headers()
        )
        return self._parse_results(
            (data or {}).get("results", []), _norm(album), artist, strict
        )

    def search_artist_releases(self, artist):
        query = urllib.parse.urlencode({"artist": artist, "type": "release"})
        data = self._get(
            "https://api.discogs.com/database/search?" + query, self._discogs_headers()
        )
        return self._parse_results((data or {}).get("results", []), None, artist, False)

    def release_detail(self, release_id, force=False):
        cache_key = f"release:{release_id}"
        if not force and cache_key in self._cache:
            return self._cache[cache_key]
        data = self._get(
            f"https://api.discogs.com/releases/{release_id}", self._discogs_headers()
        )
        if data is None:
            return None
        detail = {
            "title": data.get("title", ""),
            "year": str(data.get("year") or ""),
            "genres": data.get("genres") or [],
            "styles": data.get("styles") or [],
            "discogs_id": data.get("id"),
            "master_id": data.get("master_id"),
            "artists": [a.get("name", "") for a in data.get("artists") or []],
            "label": (data.get("labels") or [{}])[0].get("name"),
            "catalog_number": data.get("catalog_number"),
        }
        self._cache[cache_key] = detail
        return detail

    def isrc_to_discogs(self, isrc):
        cache_key = f"isrc:{isrc}"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            return entry.get("release_id")
        release_id = None
        try:
            data = self._throttled_mb(f"https://musicbrainz.org/ws/2/isrc/{isrc}?fmt=json")
            recordings = (data or {}).get("recordings") or []
            if recordings:
                release_id = self._discogs_from_recordings(recordings)
        except Exception:
            release_id = None
        self._cache[cache_key] = {"release_id": release_id}
        return release_id

    def _throttled_mb(self, url):
        return self._get(url, {"User-Agent": MB_UA})

    def _discogs_from_recordings(self, recordings):
        for recording in recordings[:2]:
            try:
                data = self._throttled_mb(
                    "https://musicbrainz.org/ws/2/recording/"
                    f"{recording['id']}?fmt=json&inc=releases"
                )
                releases = (data or {}).get("releases") or []
                for release in releases[:3]:
                    detail = self._throttled_mb(
                        "https://musicbrainz.org/ws/2/release/"
                        f"{release['id']}?fmt=json&inc=url-rels"
                    )
                    for relation in (detail or {}).get("relations", []):
                        url = relation.get("url", {}).get("resource", "")
                        if "discogs.com" not in url:
                            continue
                        match = re.search(r"discogs\.com/(release|master)/(\d+)", url)
                        if match and match.group(1) == "release":
                            return match.group(2)
            except Exception:
                continue
        return None

    def flush(self):
        self._save_cache()


def _read_genre_tag(file_path):
    try:
        if file_path.suffix.lower() == ".flac":
            tags = FLAC(file_path).tags or {}
            value = tags.get("genre") or tags.get("GENRE")
            if isinstance(value, list):
                value = value[0] if value else ""
            return (str(value or "")).strip()
        audio = ID3(file_path)
        frame = audio.get("TCON")
        if frame is not None:
            return str(frame.text[0]).strip()
    except Exception:
        pass
    return ""


def _write_genre_tag(file_path, bucket):
    if file_path.suffix.lower() == ".flac":
        audio = FLAC(file_path)
        if audio.tags is None:
            audio.add_tags()
        audio["GENRE"] = bucket
        audio.save()
    else:
        try:
            audio = ID3(file_path)
        except ID3NoHeaderError:
            audio = ID3()
        audio.delall("TCON")
        audio.add(TCON(encoding=3, text=bucket))
        audio.save(v2_version=3)


class GenreFiller:
    def __init__(self, library):
        self._library = library
        self._report_lines = []
        self.written_files = 0
        self.written_tracks = 0

    def log(self, text):
        print(t.log(text))
        self._report_lines.append(text)

    def warn(self, text):
        print(t.warning(text))
        self._report_lines.append(f"WARNING: {text}")

    def run(self, track_ids=None, force=False):
        started = time.monotonic()
        client = DiscogsClient(self)
        self.log(
            "discogs: "
            + ("authenticated (60 req/min)" if client.authenticated
               else "anonymous (25 req/min; add a token under 'discogs' in credentials.yml to speed this up)")
        )
        rows = self._library.genre_scan_rows(track_ids=track_ids)
        tracks = {}
        for track_id, title, artist, album, isrc, genre, fmt, path, root in rows:
            entry = tracks.setdefault(track_id, {
                "title": title, "artist": artist, "album": album,
                "isrc": isrc, "genre": genre, "files": [],
            })
            entry["files"].append(Path(unicodedata.normalize("NFC", f"{root}/{path}")))
        todo = [
            (track_id, entry) for track_id, entry in tracks.items()
            if force or not (entry["genre"] or "").strip()
        ]
        self.log(f"{len(tracks)} tracks in db, {len(todo)} without genre")
        if not todo:
            return True

        # Network phase runs in a thread pool: Discogs and MusicBrainz have
        # separate per-host rate budgets, and while the user answers a review
        # prompt the remaining candidates keep resolving in the background.
        workers = 6 if client.authenticated else 4
        resolved = 0
        queue = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(self._resolve, client, track_id, entry)
                for track_id, entry in todo
            ]
            for index, future in enumerate(as_completed(futures), 1):
                try:
                    track_id, entry, bucket, style, matches = future.result()
                except Exception as error:
                    self.warn(f"resolve failed: {error}")
                    continue
                if bucket:
                    self._apply(track_id, entry, bucket, style)
                    resolved += 1
                else:
                    queue.append((track_id, entry, matches))
                if index % 10 == 0 or index == len(futures):
                    self.log(
                        f"{index}/{len(futures)} resolved, "
                        f"{resolved} tagged, {len(queue)} to review "
                        f"({client.calls} api calls)"
                    )
        client.flush()
        queue.sort(key=lambda item: ((item[1]["album"] or ""), (item[1]["title"] or "")))

        self.log(
            f"auto pass: {resolved} track(s) tagged, {len(queue)} left for review "
            f"({client.calls} api calls, {time.monotonic()-started:.0f}s)"
        )
        if queue:
            self._review_pass(client, queue)
            client.flush()
        client.flush()
        self._dump_report()
        self.log(f"done: {self.written_tracks} track(s) tagged, {self.written_files} file(s) written")
        return self.written_tracks > 0 or not queue

    def _search_strict(self, client, entry, album, first_artist):
        # Each query gets its own cache key, so an old cached miss on the raw
        # "(Radio Edit)" title no longer hides a hit on the cleaned one.
        queries = []
        for q in (album, clean_query(album), clean_query((entry["title"] or "").strip())):
            q = (q or "").strip()
            if q and all(_norm(q) != _norm(existing) for existing in queries):
                queries.append(q)
        for query in queries:
            cache_key = f"search:{_norm(query)}||{_norm(first_artist)}"
            cached = client.cached(cache_key)
            if cached is not None:
                found = cached.get("matches", [])
            else:
                try:
                    found = client.search_release(query, first_artist)
                except Exception as error:
                    self.warn(f"search failed for '{query}': {error}")
                    return []
                client.store(cache_key, {"matches": (found or [])[:5]})
            if found:
                return found
        return []

    def _resolve(self, client, track_id, entry):
        # search by album/artist -> ISRC fallback (MusicBrainz) -> release
        # detail; everything goes through the thread-safe DiscogsClient.
        album = (entry["album"] or "").strip()
        first_artist = (entry["artist"] or "").split(",")[0].strip()
        matches = self._search_strict(client, entry, album, first_artist) if album else []
        if not matches:
            isrc = (entry["isrc"] or "").strip()
            if isrc:
                release_id = client.isrc_to_discogs(isrc)
                if release_id:
                    detail = client.release_detail(release_id)
                    if detail:
                        bucket = bucket_for(detail.get("genres"), detail.get("styles"))
                        style = (detail.get("styles") or [None])[0] or ""
                        return track_id, entry, bucket, style, matches
        detail = client.release_detail(matches[0]["id"]) if matches else None
        bucket = bucket_for((detail or {}).get("genres"), (detail or {}).get("styles"))
        style = ((detail or {}).get("styles") or [None])[0] or ""
        return track_id, entry, bucket, style, matches

    def _apply(self, track_id, entry, bucket, style):
        errors = []
        for file_path in entry["files"]:
            if not file_path.is_file():
                continue
            if _read_genre_tag(file_path) == bucket:
                continue
            try:
                _write_genre_tag(file_path, bucket)
                self.written_files += 1
            except Exception as error:
                errors.append(f"{file_path.name}: {error}")
        self._library.set_track_genre(track_id, bucket, style)
        self.written_tracks += 1
        for error in errors:
            self.warn(f"tag write failed: {error}")

    def _review_pass(self, client, queue):
        from InquirerPy import prompt as inquirer_prompt
        from InquirerPy.base.control import Choice

        answer = inquirer_prompt([{
            "type": "confirm", "name": "confirm",
            "message": f"manually review {len(queue)} track(s) without a confident genre?",
            "default": False,
        }])
        if not answer.get("confirm"):
            return
        for index, (track_id, entry, matches) in enumerate(queue, 1):
            album = (entry["album"] or "").strip()
            title = (entry["title"] or "").strip()
            first_artist = (entry["artist"] or "").split(",")[0].strip()
            label = f"{entry['title']} - {entry['artist']} ({index}/{len(queue)})"
            candidates = []
            seen = set()

            def add(items):
                for item in items or []:
                    if item["id"] not in seen:
                        seen.add(item["id"])
                        candidates.append(item)

            add(matches)
            if len(candidates) < 3 and first_artist:
                # The strict search only keeps exact title hits, which miss
                # most singles/EDM releases; widen with non-strict album and
                # track-title searches so the reviewer actually sees options.
                queries = []
                for q in (album, clean_query(album), title, clean_query(title)):
                    if q and all(_norm(q) != _norm(existing) for existing in queries):
                        queries.append(q)
                for query in queries:
                    try:
                        add(client.search_release(query, first_artist, strict=False))
                    except Exception as error:
                        self.warn(f"search failed for '{query}': {error}")
                if not candidates:
                    # Track never released on its own: offer the artist's
                    # discography so the user can pick the parent album.
                    try:
                        add(client.search_artist_releases(first_artist))
                    except Exception as error:
                        self.warn(f"artist search failed for '{first_artist}': {error}")
            while True:
                options = []
                for candidate in candidates[:10]:
                    genres = candidate.get("genres") or []
                    styles = candidate.get("styles") or []
                    if not genres:
                        detail = client.release_detail(candidate["id"]) or {}
                        genres = detail.get("genres") or []
                        styles = detail.get("styles") or []
                    taxonomy = " • ".join(
                        p for p in (
                            "/".join(genres),
                            "/".join(styles[:3]),
                        ) if p
                    )
                    options.append(Choice(value=candidate, name=(
                        f"{candidate['title']} ({candidate['year'] or '?'})"
                        + (f" • {taxonomy}" if taxonomy else "")
                    )))
                options.append(Choice(value="__search__", name="nova pesquisa..."))
                options.append(Choice(value=None, name="skip this track"))
                chosen = inquirer_prompt([{
                    "type": "list", "name": "choice",
                    "message": f"discogs release for '{label}':",
                    "choices": options,
                }]).get("choice")
                if chosen is None:
                    break
                if chosen == "__search__":
                    query = inquirer_prompt([{
                        "type": "input", "name": "query",
                        "message": "pesquisar no discogs por album/single:",
                    }]).get("query", "").strip()
                    if query and first_artist:
                        try:
                            add(client.search_release(query, first_artist, strict=False))
                        except Exception as error:
                            self.warn(f"search failed for '{query}': {error}")
                    continue
                detail = client.release_detail(chosen["id"]) or {}
                bucket = bucket_for(detail.get("genres"), detail.get("styles"))
                if not bucket:
                    self.warn(f"no bucket mapped for {detail.get('genres')}/{detail.get('styles')}")
                    continue
                style = (detail.get("styles") or [""])[0]
                self._apply(track_id, entry, bucket, style)
                self.log(f"review tagged: {label} -> {bucket}")
                break

    def _dump_report(self):
        try:
            log_dir = Path("~/.config/spotidal/logs").expanduser()
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            (log_dir / f"genres-{stamp}.log").write_text("\n".join(self._report_lines) + "\n")
            print(t.log_grey(f"genre report saved to {log_dir}/genres-{stamp}.log"))
        except OSError:
            pass
