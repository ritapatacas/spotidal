import random
import re
import sqlite3
import time
import urllib.parse
from pathlib import Path

from .genre import BudgetExhausted, clean_query
from .helpers.type.file import Files
from .library import _normalize_match_text, _now

BASE_URL = "https://rateyourmusic.com"
CACHE_PATH = Path("~/.config/spotidal/rym_cache.json").expanduser()
PROFILE_DIR = Path("~/.config/spotidal/rym-profile").expanduser()

# Confirmed live 2026-09-08 against real release/search pages (logged-in
# session, ~6 requests, no interstitial). RYM changes markup without notice --
# if these start returning nothing, re-verify by hand before assuming a bug.
SEARCH_ROW_SELECTOR = "tr.infobox"
SEARCH_ARTIST_SELECTOR = "a.artist"
SEARCH_RELEASE_SELECTOR = "a.searchpage"
INFO_HEADER_SELECTOR = ".info_hdr"
GENRE_PRIMARY_SELECTOR = ".release_pri_genres a.genre"
GENRE_SECONDARY_SELECTOR = ".release_sec_genres a.genre"
DESCRIPTOR_SELECTOR = ".release_pri_descriptors"

# The "are you a robot" interstitial was never triggered during the spike, so
# this signature is Cloudflare's generic challenge page, not RYM's specific
# one. Confirm/adjust the first time a real challenge is seen (see
# docs/agents/workflows.md) -- do not assume this is exhaustive.
CHALLENGE_TITLE_MARKERS = ("just a moment", "are you a robot", "attention required")
CHALLENGE_BODY_MARKERS = (
    "checking your browser", "cf-browser-verification", "challenge-platform",
)

_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")


class SiteBlocked(Exception):
    """RYM would not serve the page after pausing for a human to resolve a challenge."""


class RymClient:
    """Thin wrapper over a real, visible, persistent Chrome via Playwright.

    Unlike DiscogsClient this never talks to an API: RYM has none, and every
    request is a real page load in a browser a human can see and intervene
    in. Pacing and the challenge pause exist to keep the request volume low
    -- the only thing that matters against an anti-bot system -- not to
    defeat it.
    """

    MIN_DELAY = 10
    MAX_DELAY = 25
    LONG_PAUSE_EVERY = 20
    LONG_PAUSE_RANGE = (60, 120)
    CHALLENGE_TIMEOUT = 600
    CHALLENGE_POLL = 5
    MAX_CHALLENGES_PER_SESSION = 3
    CHECKPOINT_EVERY = 20

    def __init__(self, report, max_pages=80, min_delay=None, max_delay=None):
        self._report = report
        self._max_pages = max_pages
        self._min_delay = min_delay if min_delay is not None else self.MIN_DELAY
        self._max_delay = max_delay if max_delay is not None else self.MAX_DELAY
        self._pages = 0
        self._challenges = 0
        self._playwright = None
        self._context = None
        self._page = None
        self._cache = self._load_cache()
        self._cache_dirty = 0

    @property
    def pages(self):
        return self._pages

    # ---- cache --------------------------------------------------------

    def _load_cache(self):
        import json

        try:
            return json.loads(CACHE_PATH.read_text())
        except (FileNotFoundError, ValueError, OSError):
            return {}

    def _save_cache(self):
        import json

        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(json.dumps(self._cache, indent=1), encoding="utf-8")
        except OSError as error:
            self._report.warn(f"rym: unable to save cache: {error}")

    def cached(self, key):
        return self._cache.get(key)

    def store(self, key, value):
        self._cache[key] = value
        self._cache_dirty += 1
        if self._cache_dirty >= self.CHECKPOINT_EVERY:
            self.flush()

    def flush(self):
        self._save_cache()
        self._cache_dirty = 0

    # ---- browser lifecycle ---------------------------------------------

    def _ensure_browser(self):
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        # Playwright 1.55+ adds --no-sandbox by default (chromiumSandbox
        # defaults to false). Real Chrome on macOS does not understand that
        # Linux-only flag and prints a warning banner for it; the sandbox is
        # already enforced by macOS here, so opt back in to drop the flag.
        self._context = self._playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR), channel="chrome", headless=False,
            chromium_sandbox=True,
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    def close(self):
        if self._context is not None:
            self._context.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._context = self._page = self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # ---- pacing and challenge handling -----------------------------------

    def _pace(self):
        if self._pages and self._pages % self.LONG_PAUSE_EVERY == 0:
            pause = random.uniform(*self.LONG_PAUSE_RANGE)
            self._report.log(f"rym: long pause {pause:.0f}s after {self._pages} pages")
            time.sleep(pause)
        else:
            time.sleep(random.uniform(self._min_delay, self._max_delay))

    def _looks_like_challenge(self):
        title = (self._page.title() or "").casefold()
        if any(marker in title for marker in CHALLENGE_TITLE_MARKERS):
            return True
        try:
            body = (self._page.inner_text("body") or "")[:2000].casefold()
        except Exception:
            body = ""
        return any(marker in body for marker in CHALLENGE_BODY_MARKERS)

    def _wait_for_human(self, url):
        """Pause for a human to resolve the interstitial -- never a bypass.

        The interstitial is expected to go away once solved. RYM sometimes
        instead answers with a test that *renews in place* every few seconds,
        one checkbox solve leading straight to the next: the session has been
        flagged and no solving helps. Each visible renewal burns one budget
        slot (`MAX_CHALLENGES_PER_SESSION`); once the budget is spent the run
        stops and checkpoints instead of fighting the site for the full
        timeout. A challenge that simply sits still (human still walking over)
        is not a renewal and waits out the timeout as designed.
        """
        from ..view.sound import play_task_done

        self._challenges += 1
        if self._challenges > self.MAX_CHALLENGES_PER_SESSION:
            raise SiteBlocked(
                f"more than {self.MAX_CHALLENGES_PER_SESSION} challenges this "
                "session; the site is unhappy, stopping so the run can resume later"
            )
        self._report.warn(
            f"rym: challenge detected at {url}; resolve it in the visible "
            f"browser window (waiting up to {self.CHALLENGE_TIMEOUT // 60} min). "
            f"If a new test keeps appearing right after the previous one, the "
            f"session was flagged -- it will stop by itself after "
            f"{self.MAX_CHALLENGES_PER_SESSION} renewals."
        )
        play_task_done("ping")
        waited = 0
        last_fingerprint = None
        while waited < self.CHALLENGE_TIMEOUT:
            time.sleep(self.CHALLENGE_POLL)
            waited += self.CHALLENGE_POLL
            if not self._looks_like_challenge():
                self._report.log("rym: challenge resolved, continuing")
                return
            fingerprint = self._challenge_fingerprint()
            if last_fingerprint is not None and fingerprint != last_fingerprint:
                self._challenges += 1
                if self._challenges > self.MAX_CHALLENGES_PER_SESSION:
                    raise SiteBlocked(
                        f"more than {self.MAX_CHALLENGES_PER_SESSION} challenges "
                        "this session; the interstitial keeps renewing and the "
                        "site is unhappy, stopping so the run can resume later"
                    )
                self._report.warn(
                    f"rym: challenge renewed in place at {url} "
                    f"({self.MAX_CHALLENGES_PER_SESSION - self._challenges} "
                    f"challenge slot(s) left)"
                )
            last_fingerprint = fingerprint
        raise SiteBlocked(
            f"challenge at {url} not resolved within {self.CHALLENGE_TIMEOUT // 60} min"
        )

    def _challenge_fingerprint(self):
        """A cheap identity for the current interstitial, to spot in-place renewals."""
        try:
            body = self._page.inner_text("body") or ""
        except Exception:
            return None
        return (self._page.title() or "", body[:4000])

    def _goto(self, url):
        self._ensure_browser()
        if self._max_pages is not None and self._pages >= self._max_pages:
            raise BudgetExhausted(f"reached the {self._max_pages} page budget")
        self._pace()
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._pages += 1
        if self._looks_like_challenge():
            self._wait_for_human(url)

    # ---- scraping -------------------------------------------------------

    def search_release(self, artist, album):
        query = f"{artist} {album}".strip()
        cache_key = f"search:{_normalize_match_text(artist)}||{_normalize_match_text(album)}"
        cached = self.cached(cache_key)
        if cached is not None:
            return cached
        url = f"{BASE_URL}/search?searchterm={urllib.parse.quote(query)}&searchtype=l"
        self._goto(url)
        candidates = []
        for row in self._page.query_selector_all(SEARCH_ROW_SELECTOR):
            release_el = row.query_selector(SEARCH_RELEASE_SELECTOR)
            if not release_el:
                continue
            artist_el = row.query_selector(SEARCH_ARTIST_SELECTOR)
            href = release_el.get_attribute("href") or ""
            row_text = row.inner_text() or ""
            year_match = _YEAR_RE.search(row_text)
            candidates.append({
                "rym_path": href if href.startswith("/") else f"/{href}",
                "title": (release_el.inner_text() or "").strip(),
                "artist": (artist_el.inner_text() or "").strip() if artist_el else "",
                "year": year_match.group(0) if year_match else None,
            })
        candidates = candidates[:10]
        self.store(cache_key, candidates)
        return candidates

    def release_detail(self, rym_path):
        cache_key = f"release:{rym_path}"
        cached = self.cached(cache_key)
        if cached is not None:
            return cached
        self._goto(f"{BASE_URL}{rym_path}")
        title = artist = year = None
        for header in self._page.query_selector_all(INFO_HEADER_SELECTOR):
            label = (header.inner_text() or "").strip().casefold()
            value_el = header.evaluate_handle("el => el.nextElementSibling")
            value_el = value_el.as_element()
            if value_el is None:
                continue
            if label == "artist":
                link = value_el.query_selector("a")
                artist = ((link.inner_text() if link else value_el.inner_text()) or "").strip()
            elif label == "released":
                match = _YEAR_RE.search(value_el.inner_text() or "")
                year = match.group(0) if match else None
        title_el = self._page.query_selector(".album_title")
        if title_el:
            title_text = (title_el.inner_text() or "").strip()
            title = title_text.splitlines()[0].strip() if title_text else None
        primary = [
            (el.inner_text() or "").strip()
            for el in self._page.query_selector_all(GENRE_PRIMARY_SELECTOR)
        ]
        secondary = [
            (el.inner_text() or "").strip()
            for el in self._page.query_selector_all(GENRE_SECONDARY_SELECTOR)
        ]
        descriptors_el = self._page.query_selector(DESCRIPTOR_SELECTOR)
        descriptors = []
        if descriptors_el:
            descriptors = [
                part.strip()
                for part in (descriptors_el.inner_text() or "").split(",")
                if part.strip()
            ]
        detail = {
            "title": title,
            "artist": artist,
            "year": year,
            "primary_genres": primary,
            "secondary_genres": secondary,
            "descriptors": descriptors,
        }
        self.store(cache_key, detail)
        return detail


class _StdoutReport:
    def log(self, text):
        print(text)

    def warn(self, text):
        print(f"WARNING: {text}")


class RymTaxonomyFiller:
    """Mirrors DiscogsTaxonomyFiller's shape: release-level resolution, database-only
    writes, and harvest_log bookkeeping under source='rym' so the two harvests never
    step on each other's attempt counts.
    """

    HARVEST_SOURCE = "rym"
    MAX_UNMATCHED_ATTEMPTS = 3

    def __init__(self, database_path, report=None, max_pages=80, min_delay=None, max_delay=None):
        self.database_path = Path(database_path).expanduser().resolve()
        self._report = report or _StdoutReport()
        self._client = RymClient(
            self._report, max_pages=max_pages, min_delay=min_delay, max_delay=max_delay,
        )

    @property
    def client(self):
        return self._client

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    # ---- track selection --------------------------------------------------

    def selection_tracks(self):
        names = Files.SELECTION.load() or []
        if not names:
            return []
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in names)
            return connection.execute(
                "SELECT DISTINCT t.track_id, t.title, t.artist, t.album, t.year "
                "FROM playlists p "
                "JOIN playlist_tracks pt ON pt.playlist_id = p.playlist_id "
                "JOIN tracks t ON t.track_id = pt.track_id "
                f"WHERE p.name IN ({placeholders}) "
                "ORDER BY t.artist COLLATE NOCASE, t.album COLLATE NOCASE",
                list(names),
            ).fetchall()

    def all_tracks(self):
        selected = self.selection_tracks()
        seen = {row[0] for row in selected}
        with self._connect() as connection:
            rest = connection.execute(
                "SELECT track_id, title, artist, album, year FROM tracks "
                "ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE"
            ).fetchall()
        return selected + [row for row in rest if row[0] not in seen]

    def playlist_tracks(self, name):
        with self._connect() as connection:
            return connection.execute(
                "SELECT t.track_id, t.title, t.artist, t.album, t.year "
                "FROM playlist_tracks pt "
                "JOIN playlists p ON p.playlist_id = pt.playlist_id "
                "JOIN tracks t ON t.track_id = pt.track_id "
                "WHERE p.name = ? ORDER BY t.title COLLATE NOCASE",
                (name,),
            ).fetchall()

    # ---- release-level dedup ------------------------------------------

    def _release_groups(self, rows):
        # One request per (artist, album) pair, fanned out to every track that
        # shares it -- an album costs one page load, not one per track.
        groups = {}
        order = []
        for track_id, title, artist, album, year in rows:
            first_artist = (artist or "").split(",")[0].strip()
            key_album = (album or "").strip() or (title or "").strip()
            key = (_normalize_match_text(first_artist), _normalize_match_text(key_album))
            if key not in groups:
                groups[key] = {
                    "artist": first_artist, "album": key_album, "tracks": [],
                }
                order.append(key)
            groups[key]["tracks"].append((track_id, title, artist, album, year))
        return [groups[key] for key in order]

    # ---- matching -------------------------------------------------------

    @staticmethod
    def _tokens(text):
        return set(_normalize_match_text(text).split())

    def _accepts(self, query_album, candidate, track_year):
        cand_tokens = self._tokens(candidate.get("title", ""))
        query_tokens = self._tokens(query_album)
        if not cand_tokens or not query_tokens:
            return False
        exact = cand_tokens == query_tokens
        subset = cand_tokens <= query_tokens or query_tokens <= cand_tokens
        if not (exact or subset):
            return False
        if candidate.get("year") and track_year:
            try:
                if abs(int(candidate["year"]) - int(track_year)) > 5:
                    return False
            except ValueError:
                pass
        return True

    def resolve(self, artist, album, track_year=None):
        queries = []
        for candidate in (album, clean_query(album or "")):
            candidate = (candidate or "").strip()
            if candidate and all(
                _normalize_match_text(candidate) != _normalize_match_text(existing)
                for existing in queries
            ):
                queries.append(candidate)
        for query in queries:
            matches = self._client.search_release(artist, query) or []
            for match in matches:
                if self._accepts(query, match, track_year):
                    return match["rym_path"]
        return None

    # ---- persistence ------------------------------------------------------

    def store(self, connection, track_ids, rym_path, detail, confidence, method="search"):
        now = _now()
        primary_id = None
        for track_id in track_ids:
            connection.execute(
                "UPDATE rym_release SET is_selected=0 WHERE track_id=? AND is_selected=1 "
                "AND rym_path<>?",
                (track_id, rym_path),
            )
            row = connection.execute(
                "SELECT rym_release_id FROM rym_release WHERE track_id=? AND rym_path=?",
                (track_id, rym_path),
            ).fetchone()
            if row:
                release_id = row[0]
                connection.execute(
                    "UPDATE rym_release SET is_selected=1, confidence=?, match_method=?, "
                    "title=?, artist=?, year=?, updated_at=? WHERE rym_release_id=?",
                    (
                        confidence, method, detail.get("title"), detail.get("artist"),
                        _year_int(detail.get("year")), now, release_id,
                    ),
                )
            else:
                cursor = connection.execute(
                    "INSERT INTO rym_release(track_id, rym_path, title, artist, year, "
                    "confidence, match_method, is_selected, review_status, selection_method, "
                    "created_at, updated_at) VALUES(?,?,?,?,?,?,?,1,'pending','automatic',?,?)",
                    (
                        track_id, rym_path, detail.get("title"), detail.get("artist"),
                        _year_int(detail.get("year")), confidence, method, now, now,
                    ),
                )
                release_id = cursor.lastrowid
            if primary_id is None:
                primary_id = release_id
        genres = [(name, "primary") for name in detail.get("primary_genres") or []]
        genres += [(name, "secondary") for name in detail.get("secondary_genres") or []]
        genres += [(name, "descriptor") for name in detail.get("descriptors") or []]
        for name, kind in genres:
            connection.execute(
                "INSERT OR IGNORE INTO rym_release_genre(rym_release_id, name, kind) "
                "VALUES(?,?,?)",
                (primary_id, name, kind),
            )

    def _harvest_state(self, connection):
        return {
            row[0]: (row[1], row[2])
            for row in connection.execute(
                "SELECT track_id, attempts, outcome FROM harvest_log WHERE source = ?",
                (self.HARVEST_SOURCE,),
            )
        }

    def _record_attempt(self, connection, track_id, outcome):
        connection.execute(
            "INSERT INTO harvest_log(track_id, source, attempts, last_attempt_at, outcome) "
            "VALUES(?, ?, 1, ?, ?) "
            "ON CONFLICT(track_id, source) DO UPDATE SET "
            "attempts = attempts + 1, last_attempt_at = excluded.last_attempt_at, "
            "outcome = excluded.outcome",
            (track_id, self.HARVEST_SOURCE, _now(), outcome),
        )

    def _clear_attempt(self, connection, track_id):
        connection.execute(
            "DELETE FROM harvest_log WHERE track_id = ? AND source = ?",
            (track_id, self.HARVEST_SOURCE),
        )

    def _bound_track_ids(self, connection):
        return {
            row[0]
            for row in connection.execute(
                "SELECT track_id FROM rym_release WHERE is_selected = 1"
            )
        }

    def harvest(self, rows, retry_unmatched=False):
        """Resolve (artist, album) release groups on RYM and persist the taxonomy.

        Writes only rym_release/rym_release_genre -- never tracks.genre/style, never
        file tags. Safe to interrupt: progress lives in the database and the JSON
        cache, so a relaunch skips whatever is already resolved.
        """
        stats = {"filled": 0, "skipped": 0, "unmatched": 0, "stopped": None}
        with self._connect() as connection:
            already = self._bound_track_ids(connection)
            state = self._harvest_state(connection)
        for group in self._release_groups(rows):
            pending = [
                (track_id, title, artist, album, year)
                for track_id, title, artist, album, year in group["tracks"]
                if track_id not in already
            ]
            if not pending:
                stats["skipped"] += len(group["tracks"])
                continue
            lead_track_id = pending[0][0]
            attempts, outcome = state.get(lead_track_id, (0, None))
            if (
                not retry_unmatched
                and outcome == "unmatched"
                and attempts >= self.MAX_UNMATCHED_ATTEMPTS
            ):
                stats["skipped"] += len(pending)
                continue
            track_ids = [row[0] for row in pending]
            track_year = next((row[4] for row in pending if row[4]), None)
            try:
                rym_path = self.resolve(group["artist"], group["album"], track_year)
                detail = self._client.release_detail(rym_path) if rym_path else None
            except (SiteBlocked, BudgetExhausted) as error:
                stats["stopped"] = error
                break
            if not detail or not (
                detail.get("primary_genres") or detail.get("secondary_genres")
            ):
                stats["unmatched"] += len(pending)
                with self._connect() as connection:
                    for track_id in track_ids:
                        self._record_attempt(connection, track_id, "unmatched")
                continue
            with self._connect() as connection:
                self.store(connection, track_ids, rym_path, detail, confidence=0.8)
                for track_id in track_ids:
                    self._clear_attempt(connection, track_id)
            stats["filled"] += len(pending)
            taxonomy = ", ".join(
                detail.get("primary_genres", []) + detail.get("secondary_genres", [])
            )
            self._report.log(
                f"{group['artist']} - {group['album']} -> rym:{rym_path} "
                f"[{taxonomy}] ({len(pending)} track(s))"
            )
        self._client.flush()
        return stats


def _year_int(value):
    try:
        return int(str(value)[:4]) if value else None
    except ValueError:
        return None
