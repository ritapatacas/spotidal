import atexit
import os
import json
import re
import select
from datetime import datetime
import subprocess
import sys
import termios
import threading
import time
import tty
import unicodedata
import webbrowser
from pathlib import Path
from queue import Empty, Queue
from tqdm import tqdm
from ..helpers.type.file import Files
from ..library import MusicLibrary
from ..normalize_audio import (
    BACKUP_DIR_NAME,
    CONVERTIBLE_EXTENSIONS,
    archive_original,
    convert_to_flac,
)
from ...view.text import Text as t


QUALITY_PRIORITIES = {
    "Max": "Max,HiFi,High,Normal",
    "Atmos": "Atmos,Max,HiFi,High,Normal",
    "Master": "Master,HiFi,High,Normal",
    "HiFi": "HiFi,High,Normal",
    "High": "High,Normal",
    "Normal": "Normal",
}
_KNOWN_AUDIO_EXTENSION = re.compile(
    r"\.(flac|mp3|" + "|".join(ext.lstrip(".") for ext in CONVERTIBLE_EXTENSIONS) + r")$",
    re.IGNORECASE,
)
DEFAULT_DOWNLOAD_PATH = os.path.expanduser("~/Spotidal")
CONVERSION_MESSAGES = Queue()
TIDEKEEPER_SETUP_LOCK = threading.Lock()
DATABASE_IMPORT_LOCK = threading.Lock()
ACCESS_TOKEN_LOG_LOCK = threading.Lock()
ACCESS_TOKEN_LOGGED = False
_ACTIVE_DOWNLOADS_LOCK = threading.Lock()
_ACTIVE_DOWNLOADS = 0
STDIN_MONITOR_LOCK = threading.Lock()
CANCEL_ALL_DOWNLOADS = threading.Event()
_ACTIVE_PROCESSES_LOCK = threading.Lock()
_ACTIVE_PROCESSES = set()
# Adaptive extra delay applied before starting each new download, on top of
# tidekeeper's own internal 429 backoff. Grows when TIDAL rate-limits us,
# decays back down once requests start going through cleanly again.
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_DELAY = 0.0
RATE_LIMIT_DELAY_STEP = 2.0
RATE_LIMIT_DELAY_MAX = 25.0


def _note_rate_limited():
    global _RATE_LIMIT_DELAY
    with _RATE_LIMIT_LOCK:
        before = _RATE_LIMIT_DELAY
        _RATE_LIMIT_DELAY = min(RATE_LIMIT_DELAY_MAX, _RATE_LIMIT_DELAY + RATE_LIMIT_DELAY_STEP)
        after = _RATE_LIMIT_DELAY
    if after != before:
        tqdm.write(t.log_grey(f"delay between requests: {before:.1f}s -> {after:.1f}s"))


def _decay_rate_limit_delay():
    global _RATE_LIMIT_DELAY
    with _RATE_LIMIT_LOCK:
        before = _RATE_LIMIT_DELAY
        _RATE_LIMIT_DELAY = max(0.0, _RATE_LIMIT_DELAY - RATE_LIMIT_DELAY_STEP / 2)
        after = _RATE_LIMIT_DELAY
    if after != before:
        tqdm.write(t.log_grey(f"delay between requests: {before:.1f}s -> {after:.1f}s"))


def _current_rate_limit_delay():
    with _RATE_LIMIT_LOCK:
        return _RATE_LIMIT_DELAY


# Tracks download *attempts* (one per download_url() call), not raw HTTP
# requests: tidekeeper makes several actual API calls per track internally
# and we have no visibility into that count from the outside.
_REQUEST_LOG_LOCK = threading.Lock()
_REQUEST_TIMESTAMPS = []


def _note_request():
    with _REQUEST_LOG_LOCK:
        _REQUEST_TIMESTAMPS.append(time.monotonic())


def _request_counts():
    now = time.monotonic()
    with _REQUEST_LOG_LOCK:
        total = len(_REQUEST_TIMESTAMPS)
        last_hour = sum(1 for t in _REQUEST_TIMESTAMPS if now - t <= 3600)
        last_minute = sum(1 for t in _REQUEST_TIMESTAMPS if now - t <= 60)
    return total, last_hour, last_minute


_TIDEKEEPER_VERIFIED = False
_TIDEKEEPER_PROGRESS_CONFIGURED = False
_TIDEKEEPER_CONFIGURED_SETTINGS = None


class TidalSessionStaleError(RuntimeError):
    """Raised when TIDAL rejects the saved session's API client."""


class DownloadCancelled(RuntimeError):
    """Raised when the user confirms stopping the current download batch."""


def check_and_install_tidekeeper():
    # Spawns a subprocess just to check the version; with several download
    # threads each calling this once per track under TIDEKEEPER_SETUP_LOCK,
    # that serialized subprocess-per-track adds real per-track latency for
    # no benefit once we already know it's installed. Verify once per
    # process instead.
    global _TIDEKEEPER_VERIFIED
    if _TIDEKEEPER_VERIFIED:
        return
    try:
        result = subprocess.run(
            ["tidekeeper", "--version"], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise Exception("> tidekeeper not installed")
    except Exception:
        print(t.log("tidekeeper not found, installing..."))
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "tidekeeper"]
        )
    _TIDEKEEPER_VERIFIED = True


def configure_tidekeeper_formats(settings):
    # Same reasoning as check_and_install_tidekeeper: this does file I/O
    # under the shared setup lock on every single track. Skip the rewrite
    # when the relevant settings haven't changed since the last call.
    global _TIDEKEEPER_CONFIGURED_SETTINGS
    tidekeeper = settings.get("tidekeeper", {})
    if _TIDEKEEPER_CONFIGURED_SETTINGS == tidekeeper:
        return
    config_path = Path(os.path.expanduser("~/.tidal-dl.json"))
    try:
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
        config["albumFolderFormat"] = tidekeeper.get(
            "albumFolderFormat", "{ArtistName}/{AlbumTitle}"
        )
        config["trackFileFormat"] = tidekeeper.get(
            "trackFileFormat", "{TrackNumber} - {ArtistName} - {TrackTitle}{ExplicitFlag}"
        )
        config["usePlaylistFolder"] = False
        config_path.write_text(json.dumps(config, indent=4))
        _TIDEKEEPER_CONFIGURED_SETTINGS = tidekeeper
    except (OSError, json.JSONDecodeError, TypeError):
        pass


def configure_tidekeeper_progress():
    global _TIDEKEEPER_PROGRESS_CONFIGURED
    if _TIDEKEEPER_PROGRESS_CONFIGURED:
        return
    try:
        from tidal_dl.paths import PATHS
        from tidal_dl.settings import SETTINGS

        SETTINGS.read(PATHS.getProfilePath())
        SETTINGS.showProgress = True
        SETTINGS.multiThread = False
        SETTINGS.save()
        _TIDEKEEPER_PROGRESS_CONFIGURED = True
    except Exception:
        pass


def default_Settings():
    check_and_install_tidekeeper()


def _remove_partial_files(download_path):
    if not download_path:
        return 0
    root = Path(os.path.expanduser(download_path))
    if not root.is_dir():
        return 0
    removed_parts = 0
    for _ in range(5):
        partials = list(root.rglob("*.part.parts"))
        if not partials:
            return removed_parts
        for partial in partials:
            try:
                if partial.is_dir():
                    for directory, directories, files in os.walk(partial, topdown=False):
                        for filename in files:
                            try:
                                os.unlink(os.path.join(directory, filename))
                            except OSError:
                                pass
                        for child in directories:
                            try:
                                os.rmdir(os.path.join(directory, child))
                            except OSError:
                                pass
                    os.rmdir(partial)
                    removed_parts += 1
                else:
                    partial.unlink()
            except OSError:
                pass
        time.sleep(0.25)
    return removed_parts


def clean_tmp(download_path):
    return _remove_partial_files(download_path)


def _enter_download():
    global _ACTIVE_DOWNLOADS
    with _ACTIVE_DOWNLOADS_LOCK:
        _ACTIVE_DOWNLOADS += 1


def _exit_download():
    global _ACTIVE_DOWNLOADS
    with _ACTIVE_DOWNLOADS_LOCK:
        _ACTIVE_DOWNLOADS -= 1
        if _ACTIVE_DOWNLOADS <= 0:
            # Batch fully drained; clear any cancel request so it doesn't
            # carry over and immediately kill the next, unrelated batch.
            CANCEL_ALL_DOWNLOADS.clear()


def _safe_remove_partial_files(download_path):
    # _remove_partial_files sweeps every *.part.parts directory under the
    # shared download tree, not just this call's own track. That's only
    # safe when this is the sole in-flight download; with several tracks
    # downloading concurrently (e.g. the missing-tracks doctor's worker
    # threads) it would delete chunk files a sibling thread is still
    # writing. Skip the sweep while other downloads are active; a later
    # solo call (or the explicit 'clean tmp files' menu option) will
    # still catch any leftovers.
    with _ACTIVE_DOWNLOADS_LOCK:
        solo = _ACTIVE_DOWNLOADS <= 1
    return _remove_partial_files(download_path) if solo else 0


def _flac_files(download_path):
    root = Path(download_path)
    if not root.is_dir():
        return set()
    return {
        file_path
        for file_path in root.rglob("*.flac")
        if not file_path.name.startswith("._")
        and ".tmp." not in file_path.name
        and ".part" not in file_path.name
    }


def _stray_audio_files(download_path):
    root = Path(download_path)
    if not root.is_dir():
        return set()
    return {
        file_path
        for extension in CONVERTIBLE_EXTENSIONS
        for file_path in root.rglob(f"*{extension}")
        if not file_path.name.startswith("._")
        and ".tmp." not in file_path.name
        and BACKUP_DIR_NAME not in file_path.relative_to(root).parts
    }


def _convert_stray_audio_files(download_path, previous_stray_files):
    # TIDAL sometimes serves a non-FLAC fallback (e.g. m4a) when the
    # requested quality isn't available lossless; normalize it in place so
    # the flac directory only ever holds .flac files. Scoped to files that
    # appeared during this download, so it never touches unrelated
    # pre-existing stray files elsewhere in the library.
    root = Path(download_path)
    new_stray_files = _stray_audio_files(download_path) - previous_stray_files
    for file_path in new_stray_files:
        output_file = file_path.with_suffix(".flac")
        if output_file.exists():
            continue
        if convert_to_flac(file_path, output_file):
            archive_original(file_path, root)
            tqdm.write("\n" + t.log_grey(
                f"converted {file_path.name} -> {output_file.name}"
            ))


def _tidal_track_id(url):
    parts = [part for part in url.split("/") if part]
    try:
        index = parts.index("track")
    except ValueError:
        return None
    return parts[index + 1] if index + 1 < len(parts) else None


def _format_access_token_message(message):
    match = re.search(
        r"access token good for (?:(\d+) hours?,? )?(\d+) minutes?"
        r"(?:, \d+ seconds?)?\.?$",
        message,
    )
    if not match:
        return message
    hours, minutes = match.groups()
    duration = f"{hours}h " if hours else ""
    return f"access token good for {duration}{minutes}min"


def _normalize_match_text(text):
    # TIDAL reports titles in NFC while macOS normalizes new filenames to NFD;
    # compare on a single form or accented tracks never match their own files.
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFC", text).casefold())


def _title_matches_file(title, file_path):
    title = unicodedata.normalize("NFC", title).casefold()
    stem = unicodedata.normalize("NFC", file_path.stem).casefold()
    if title in stem:
        return True
    # Filenames get punctuation (quotes, colons, "?", "'", accents-adjacent
    # symbols) stripped by tidekeeper, but the reported title doesn't — so
    # fall back to a punctuation-insensitive comparison.
    normalized_title = _normalize_match_text(title)
    return bool(normalized_title) and normalized_title in _normalize_match_text(stem)


def _report_downloads(output, download_path, previous_files):
    global ACCESS_TOKEN_LOGGED
    current_files = _flac_files(download_path)
    # Titles reported by tidekeeper can diverge from the sanitized filename it
    # writes to disk (quotes, colons, etc. get stripped), which breaks substring
    # matching below. When exactly one new file shows up for a genuinely
    # downloaded (non-skip) track, trust that unambiguous new file instead.
    new_files = current_files - previous_files
    reported_files = set()
    skipped_files = set()
    skipped_titles = []
    for line in output.splitlines():
        if "AccessToken" in line:
            with ACCESS_TOKEN_LOG_LOCK:
                if not ACCESS_TOKEN_LOGGED:
                    message = line.split("] ", 1)[-1].replace("AccessToken", "access token")
                    message = _format_access_token_message(message)
                    tqdm.write("\n" + t.busy(message + "\n"))
                    ACCESS_TOKEN_LOGGED = True
        elif "[ERR]" in line:
            tqdm.write(t.error(line.split("] ", 1)[-1]))
        elif "[SUCCESS]" in line:
            message = line.split("] ", 1)[-1]
            title = message.split(" (skip:", 1)[0].strip()
            # For some skips tidekeeper reports the on-disk filename (with
            # extension) instead of the clean track title.
            title = _KNOWN_AUDIO_EXTENSION.sub("", title)
            if " (skip:" in message:
                skipped_titles.append(title)
                # A file may exist on disk but not yet be indexed in the DB.
                matches = {
                    file_path
                    for file_path in current_files
                    if _title_matches_file(title, file_path)
                }
                reported_files.update(matches)
                skipped_files.update(matches)
                continue
            if len(new_files) == 1:
                reported_files.update(new_files)
                continue
            # Match only among files that appeared during *this* download,
            # not the whole library — a generic/short title (e.g. "Love")
            # can substring-match dozens of unrelated pre-existing tracks,
            # and every match here gets import_file()'d with this track's
            # tidal_id, corrupting all of them. Only fall back to the full
            # library if literally nothing new showed up this run (e.g. a
            # timing race on the before/after snapshot) — better than
            # silently skipping the import entirely.
            search_pool = new_files or current_files
            matches = [
                file_path
                for file_path in search_pool
                if _title_matches_file(title, file_path)
            ]
            reported_files.update(matches)

    return sorted(reported_files), [
        line.split("] ", 1)[-1].split(" (skip:", 1)[0].strip()
        for line in output.splitlines()
        if "[SUCCESS]" in line and " (skip:" not in line
    ], skipped_titles, skipped_files


def pop_conversion_messages():
    messages = []
    while True:
        try:
            messages.append(CONVERSION_MESSAGES.get_nowait())
        except Empty:
            return messages


def _wait_for_conversion(process, output_file, output_root):
    if process.wait() == 0:
        CONVERSION_MESSAGES.put(
            t.log(
                "mp3 conversion complete "
                f"{t.grey(str(output_file.relative_to(output_root)))}"
            )
        )
    else:
        CONVERSION_MESSAGES.put(
            t.error(f"mp3 conversion failed {t.grey(str(output_file))}")
        )


def kill_all_active_downloads():
    # Called on interpreter shutdown/KeyboardInterrupt: a hung tidekeeper
    # subprocess (stalled network) leaves its worker thread blocked in
    # process.wait() forever, which in turn hangs the ThreadPoolExecutor's
    # own shutdown join. Force-kill every tracked subprocess so those
    # threads unblock and the app can actually exit.
    with _ACTIVE_PROCESSES_LOCK:
        processes = list(_ACTIVE_PROCESSES)
    for process in processes:
        try:
            process.kill()
        except Exception:
            pass


atexit.register(kill_all_active_downloads)


def _run_tidekeeper(command, environment, timeout, progress_callback=None):
    output_queue = Queue()
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    with _ACTIVE_PROCESSES_LOCK:
        _ACTIVE_PROCESSES.add(process)

    def read_output():
        buffer = []
        while True:
            character = process.stdout.read(1)
            if not character:
                break
            if character in "\r\n":
                if buffer:
                    output_queue.put("".join(buffer) + "\n")
                    buffer = []
            else:
                buffer.append(character)
        if buffer:
            output_queue.put("".join(buffer) + "\n")
        output_queue.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    output = []
    deadline = time.monotonic() + timeout
    finished = False
    cancelled = False
    token_expired = False
    session_stale = False
    terminal_state = None
    # Several downloads can run concurrently (the missing-tracks doctor's
    # worker threads), but there is only one stdin/terminal. Only the thread
    # that grabs this lock watches for the escape key; the rest just poll
    # CANCEL_ALL_DOWNLOADS below. Without this, every thread independently
    # put the terminal into cbreak mode and raced to read the same escape
    # byte, corrupting terminal state and making the prompt unreliable.
    owns_stdin = sys.stdin.isatty() and STDIN_MONITOR_LOCK.acquire(blocking=False)
    if owns_stdin:
        terminal_state = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
    try:
        while time.monotonic() < deadline:
            if CANCEL_ALL_DOWNLOADS.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                cancelled = True
                break
            if terminal_state and select.select([sys.stdin], [], [], 0)[0]:
                if sys.stdin.read(1) == "\x1b":
                    # Still in cbreak mode (echo stays on), so a single
                    # keypress answers immediately without needing Enter.
                    sys.stdout.write("? stop downloading? (y/n) ")
                    sys.stdout.flush()
                    answer = ""
                    while answer not in ("y", "Y", "n", "N"):
                        answer = sys.stdin.read(1)
                    sys.stdout.write("\n")
                    if answer.lower() == "y":
                        CANCEL_ALL_DOWNLOADS.set()
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        cancelled = True
                        break
            try:
                line = output_queue.get(timeout=0.1)
                if line is None:
                    finished = True
                    break
                progress_match = re.search(r"(\d+(?:\.\d+)?)%\|", line)
                if progress_match:
                    if progress_callback:
                        progress_callback(int(progress_match.group(1)))
                    continue
                output.append(line)
                if "Expired access token. Attempting to refresh it." in line:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    token_expired = True
                    break
                if "saved login session references an API client that no longer exists" in line:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    session_stale = True
                    break
                if "[DL Track] name=" in line:
                    tqdm.write(t.busy(f"downloading '{line.split('[DL Track] name=', 1)[1].strip()}'..."))
                if "Too many requests" in line:
                    _, last_hour, last_minute = _request_counts()
                    wait_match = re.search(r"waiting (\d+) seconds?", line)
                    wait_s = wait_match.group(1) if wait_match else "?"
                    body = (
                        f"Too many requests - waiting {wait_s}s before retry. "
                        f"(attempts: {last_hour} last hour, {last_minute} last min)"
                    )
                    tail = f"@ {datetime.now():%H:%M}"
                    tqdm.write(t.warning(t.right_align(body, tail, prefix_len=2)))  # "! " from warning()
                    _note_rate_limited()
            except Empty:
                if process.poll() is not None:
                    finished = True
                    break
        if not finished and not cancelled and not token_expired and not session_stale:
            process.kill()
            process.wait()
            raise subprocess.TimeoutExpired(command, timeout)
        return process.returncode, "".join(output), cancelled, token_expired, session_stale
    finally:
        with _ACTIVE_PROCESSES_LOCK:
            _ACTIVE_PROCESSES.discard(process)
        if owns_stdin:
            if terminal_state:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, terminal_state)
            STDIN_MONITOR_LOCK.release()


def check_login():
    # tidekeeper has no login subcommand; auth happens on first download.
    # --doctor validates config, token, and local tools.
    subprocess.run(["tidekeeper", "--doctor"])


def refresh_tidekeeper_token():
    """Refresh the token stored by tidekeeper and return its credentials."""
    try:
        from tidal_dl import apiKey
        from tidal_dl.paths import PATHS
        from tidal_dl.settings import SETTINGS, TOKEN
        from tidal_dl.tidal import TIDAL_API

        SETTINGS.read(PATHS.getProfilePath())
        TOKEN.read(PATHS.getTokenPath())
        if not apiKey.isItemValid(SETTINGS.apiKeyIndex):
            SETTINGS.apiKeyIndex = apiKey.getDefaultIndex()
            SETTINGS.save()
        TIDAL_API.apiKey = apiKey.getItem(SETTINGS.apiKeyIndex)
        if not TOKEN.refreshToken or not TIDAL_API.refreshAccessToken(TOKEN.refreshToken):
            print(t.warning("tidekeeper token refresh was rejected"))
            return None
        TOKEN.accessToken = TIDAL_API.key.accessToken
        TOKEN.refreshToken = TIDAL_API.key.refreshToken
        TOKEN.expiresAfter = time.time() + int(TIDAL_API.key.expiresIn)
        TOKEN.save()
        return {
            "access_token": TOKEN.accessToken,
            "refresh_token": TOKEN.refreshToken,
        }
    except Exception as error:
        print(t.error(
            f"tidekeeper token refresh failed ({type(error).__name__}): {error}"
        ))
        return None


def login_tidekeeper():
    """Authenticate using tidekeeper's configured OAuth client."""
    from tidal_dl import apiKey
    from tidal_dl.paths import PATHS
    from tidal_dl.settings import SETTINGS, TOKEN
    from tidal_dl.tidal import TIDAL_API

    SETTINGS.read(PATHS.getProfilePath())
    TOKEN.read(PATHS.getTokenPath())
    if not apiKey.isItemValid(SETTINGS.apiKeyIndex):
        SETTINGS.apiKeyIndex = apiKey.getDefaultIndex()
        SETTINGS.save()
    TIDAL_API.apiKey = apiKey.getItem(SETTINGS.apiKeyIndex)
    tqdm.write(t.log(
        f"using tidekeeper OAuth client {SETTINGS.apiKeyIndex} "
        f"({TIDAL_API.apiKey.get('platform', 'unknown')})"
    ))

    verification_url = TIDAL_API.getDeviceCode()
    tqdm.write(t.log(f"login with the webbrowser '{verification_url}'"))
    webbrowser.open(verification_url)
    started = time.monotonic()
    while time.monotonic() - started < TIDAL_API.key.authCheckTimeout:
        if TIDAL_API.checkAuthStatus():
            TOKEN.userid = TIDAL_API.key.userId
            TOKEN.countryCode = TIDAL_API.key.countryCode
            TOKEN.accessToken = TIDAL_API.key.accessToken
            TOKEN.refreshToken = TIDAL_API.key.refreshToken
            TOKEN.expiresAfter = time.time() + int(TIDAL_API.key.expiresIn)
            TOKEN.save()
            return {
                "access_token": TOKEN.accessToken,
                "refresh_token": TOKEN.refreshToken,
            }
        time.sleep(TIDAL_API.key.authCheckInterval + 1)
    raise TimeoutError("tidekeeper OAuth login timed out")


def download_url(
    url, timeout=240, display_name=None, cleanup_partials=True, return_titles=False,
    refresh_callback=None, reauth_callback=None, progress_callback=None,
):
    _note_request()
    delay = _current_rate_limit_delay()
    if delay:
        time.sleep(delay)

    with TIDEKEEPER_SETUP_LOCK:
        check_and_install_tidekeeper()

    # todo check how many tracks the playlist has

    settings = Files.SETTINGS.load() or {}
    with TIDEKEEPER_SETUP_LOCK:
        configure_tidekeeper_formats(settings)
        configure_tidekeeper_progress()
    command = [
        "tidekeeper",
        "-q",
        settings.get("audioQuality", "Max"),
        "--quality-priority",
        QUALITY_PRIORITIES.get(
            settings.get("audioQuality", "Max"), "Max,HiFi,High,Normal"
        ),
        "-l",
        url,
    ]
    environment = os.environ.copy()
    download_path = settings.get("flacDirectory") or os.path.join(
        settings.get("downloadPath") or environment.get(
            "TIDEKEEPER_DOWNLOAD_PATH", DEFAULT_DOWNLOAD_PATH
        ),
        "flac",
    )
    download_path = os.path.abspath(os.path.expanduser(download_path))
    environment["TIDEKEEPER_DOWNLOAD_PATH"] = download_path
    effective_download_path = environment.get("TIDEKEEPER_DOWNLOAD_PATH")
    if effective_download_path:
        command[1:1] = ["-o", effective_download_path]
    previous_files = _flac_files(effective_download_path)
    previous_stray_files = _stray_audio_files(effective_download_path)

    _enter_download()
    try:
        for refresh_attempt in range(2):
            return_code, output, cancelled, token_expired, session_stale = _run_tidekeeper(
                command, environment, timeout, progress_callback
            )
            if (not token_expired and not session_stale) or refresh_attempt:
                break
            if session_stale:
                raise TidalSessionStaleError(
                    "TIDAL session is stale; go to Settings > "
                    "refresh TIDAL access token before continuing"
                )
            else:
                tqdm.write(t.busy("access token expired; refreshing before continuing"))
                callback = refresh_callback
            _safe_remove_partial_files(effective_download_path)
            try:
                refreshed = callback and callback()
            except Exception:
                refreshed = False
            if not refreshed:
                tqdm.write(t.error(
                    "unable to renew TIDAL session"
                    if session_stale else "unable to refresh TIDAL access token"
                ))
                return None
            tqdm.write(t.log(
                "TIDAL session renewed; retrying download"
                if session_stale else "TIDAL access token refreshed; retrying download"
            ))
        if cleanup_partials:
            _safe_remove_partial_files(effective_download_path)
        _convert_stray_audio_files(effective_download_path, previous_stray_files)
        completed_files, reported_titles, skipped_titles, skipped_files = _report_downloads(
            output, effective_download_path, previous_files
        )
        if (reported_titles or skipped_titles) and not completed_files:
            tqdm.write("\n" + t.warning(
                "could not match reported track(s) to a file on disk; "
                "database metadata was not updated for: "
                + ", ".join(reported_titles + skipped_titles)
            ))
        linked_existing = False
        try:
            tidal_track_id = _tidal_track_id(url)
            for flac_file in completed_files:
                for attempt in range(3):
                    try:
                        # SQLite supports concurrent readers, but serializing
                        # imports avoids write-lock contention when several
                        # download batches finish together. Only the actual
                        # import is held under the lock; the retry backoff
                        # sleep below runs outside it, so a slow/failing
                        # import doesn't block every other thread's import.
                        with DATABASE_IMPORT_LOCK:
                            library = MusicLibrary(
                                Path(effective_download_path).parent,
                                settings.get("databaseLocation"),
                            )
                            local_track_id = library.import_file(
                                flac_file, tidal_id=tidal_track_id
                            )
                        if tidal_track_id and flac_file in skipped_files:
                            linked_existing = True
                        break
                    except Exception as error:
                        if attempt == 2:
                            tqdm.write(t.error(
                                "unable to index downloaded track "
                                f"{t.grey(str(error))}"
                            ))
                        else:
                            time.sleep(attempt + 1)
        except Exception as error:
            tqdm.write(t.error(
                "unable to initialize local database "
                f"{t.grey(str(error))}"
            ))
        if return_code == 0 and settings.get("autoConvertMp3", True):
            flac_root = Path(effective_download_path)
            mp3_root = Path(settings.get("mp3Directory", flac_root.parent / "mp3")).expanduser()
            for flac_file in completed_files:
                mp3_file = mp3_root / flac_file.relative_to(flac_root)
                mp3_file = mp3_file.with_suffix(".mp3")
                conversion = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "spotidal.model.flac_to_mp3",
                        str(flac_file),
                        str(mp3_file),
                        str(flac_root.parent),
                        settings.get("databaseLocation"),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                threading.Thread(
                    target=_wait_for_conversion,
                    args=(conversion, mp3_file, mp3_root),
                    daemon=True,
                ).start()
        if cancelled:
            # Distinct from a plain failure: the caller (doctor.py) needs to
            # know this was a deliberate stop so it aborts the whole batch
            # instead of quietly moving on to the next track.
            raise DownloadCancelled("download cancelled by user")
        if return_code != 0 and not (
            (reported_titles or skipped_titles) and "[ERR]" not in output
        ):
            failed_tracks = Path(effective_download_path) / "failed-tracks.txt"
            tqdm.write(
                f"{t.red('!!')} tidekeeper failed; see "
                f"{t.grey(str(failed_tracks))} for retryable tracks"
            )
            return None
        return (
            (completed_files, reported_titles, skipped_titles, linked_existing)
            if return_titles else completed_files
        )
    except subprocess.TimeoutExpired:
        if cleanup_partials:
            _safe_remove_partial_files(effective_download_path)
        failed_tracks = Path(effective_download_path) / "failed-tracks.txt"
        tqdm.write(
            f"{t.red('!')} download timed out after {timeout} seconds; "
            f"error saved to {t.grey(str(failed_tracks))}"
        )
        return None
    finally:
        _exit_download()
        _decay_rate_limit_delay()


def download_playlist(playlist_id, timeout=240):
    download_url(f"https://tidal.com/browse/playlist/{playlist_id}", timeout)
