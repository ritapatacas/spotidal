import asyncio
import json
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import tidalapi
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from tqdm import tqdm

from .helpers.td_downloader import TidalSessionStaleError, refresh_tidekeeper_token
from .helpers.sync.playlists_handler import get_td_playlists_wrapper
from .helpers.tidalapi import get_all_playlist_tracks
from .helpers.type.file import Files
from .library import MusicLibrary, _first
from ..view.text import Text as t


# Known-good short TIDAL track used by the download doctor (verified absent
# from the library on Sep 2026); the downloaded file is verified end-to-end
# (disk, tags, db) and removed afterwards.
TEST_TRACK_ID = "128093416"
LOG_DIR = Path("~/.config/spotidal/logs").expanduser()
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


class DoctorReport:
    def __init__(self, name):
        self.name = name
        self.started = datetime.now()
        self.start = time.monotonic()
        self.lines = [f"spotidal {name} doctor - {self.started.isoformat(timespec='seconds')}"]
        self.ok_count = 0
        self.warning_count = 0
        self.failed_count = 0

    def _record(self, rendered, kind):
        plain = _ANSI_RE.sub("", rendered)
        self.lines.append(plain)
        print(rendered)

    def ok(self, text):
        self.ok_count += 1
        self._record(t.log(text), "ok")

    def info(self, text):
        self._record(t.log_grey(text), "info")

    def warn(self, text):
        self.warning_count += 1
        self._record(t.warning(text), "warn")

    def fail(self, text):
        self.failed_count += 1
        self._record(t.error(text), "fail")

    def step(self, text):
        self._record(f"\n{t.b(text)}", "step")

    @property
    def success(self):
        return self.failed_count == 0

    def finish(self):
        elapsed = time.monotonic() - self.start
        summary = (
            f"{self.name} doctor finished in {elapsed:.0f}s "
            f"({self.ok_count} ok, {self.warning_count} warnings, "
            f"{self.failed_count} failures)"
        )
        print(t.log(summary) if self.success else t.error(summary))
        self.lines.append(summary)
        stamp = self.started.strftime("%Y%m%d-%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", self.name.casefold()).strip("-")
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = LOG_DIR / f"doctor-{slug}-{stamp}.log"
            log_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
            print(t.log_grey(f"report saved to {log_path}"))
        except OSError as error:
            print(t.warning(f"unable to write doctor log: {error}"))
        return self.success


def _read_track_id(file_path):
    try:
        if file_path.suffix.lower() == ".flac":
            return _first(FLAC(file_path).tags or {}, "TRACK_ID")
        return _first(ID3(file_path), "TXXX:TRACK_ID")
    except Exception:
        return None


MP3_TARGET_BITRATE = 320_000
MP3_BITRATE_TOLERANCE = 24_000
MP3_DURATION_TOLERANCE = 1.5


def _ffprobe_stream_info(file_path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=bit_rate:format=duration",
                "-of", "json",
                str(file_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    if result.returncode != 0:
        errors = result.stderr.strip().splitlines()
        return None, errors[-1] if errors else "ffprobe failed"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return None, f"unparsable ffprobe output: {error}"
    stream = (data.get("streams") or [{}])[0]
    duration = data.get("format", {}).get("duration")
    bit_rate = stream.get("bit_rate")
    return {
        "duration": float(duration) if duration else None,
        "bit_rate": int(bit_rate) if bit_rate else None,
    }, None


def _format_track_line(track):
    artists = ", ".join(
        getattr(a, "name", str(a)) for a in (getattr(track, "artists", None) or [])
    )
    album = getattr(getattr(track, "album", None), "name", "")
    title = getattr(track, "full_name", None) or getattr(track, "name", str(track))
    line = f"{title} - {artists}"
    return f"{line} [{album}]" if album else line


class Doctor:
    def __init__(self, model, settings, downloader):
        self._model = model
        self._settings = settings
        self._downloader = downloader
        self._library = None

    def _get_library(self):
        if not self._settings.get_database_enabled():
            return None
        if self._library is None:
            self._library = MusicLibrary(
                self._settings.get_download_dir(),
                self._settings.get_database_path(),
            )
        return self._library

    def _selection_names(self):
        raw = Files.SELECTION.load() or []
        if isinstance(raw, dict):
            raw = [raw]
        names = set()
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name")
            elif item:
                name = str(item)
            else:
                name = None
            if name:
                names.add(name)
        return names

    def run_download_doctor(self):
        report = DoctorReport("download")
        td_session = (self._model.sessions or {}).get("td")

        report.step("tidekeeper")
        try:
            version = subprocess.run(
                ["tidekeeper", "--version"], capture_output=True, text=True
            )
            if version.returncode == 0:
                report.ok(f"tidekeeper available ({version.stdout.strip()})")
            else:
                report.fail("tidekeeper is not installed or not runnable")
        except FileNotFoundError:
            report.fail("tidekeeper binary not found in PATH")

        report.step("tidal access token")
        if td_session is None:
            report.fail("no TIDAL session available")
        else:
            try:
                if self._model.refresh_td_session():
                    report.ok("TIDAL access token refreshed")
                else:
                    report.fail("unable to refresh TIDAL access token")
            except Exception as error:
                report.fail(f"TIDAL token refresh error: {error}")
            try:
                if td_session.check_login():
                    report.ok("TIDAL login check passed")
                else:
                    report.fail("TIDAL session is not logged in")
            except Exception as error:
                report.fail(f"TIDAL login check error: {error}")
            try:
                if refresh_tidekeeper_token():
                    report.ok("tidekeeper token refreshed")
                else:
                    report.warn("tidekeeper token refresh was rejected")
            except Exception as error:
                report.warn(f"tidekeeper token refresh error: {error}")

        report.step("database")
        library = None
        try:
            library = self._get_library()
        except Exception as error:
            report.fail(f"database unavailable: {error}")
        if library is None:
            if self._library is None:
                report.fail("local database is disabled or unavailable")
        else:
            report.ok(
                f"database reachable ({self._settings.get_database_path()}, "
                f"{len(library.locations())} location(s))"
            )

        report.step(f"test download (track {TEST_TRACK_ID})")
        track = None
        if td_session is not None:
            try:
                track = td_session.track(TEST_TRACK_ID)
                report.ok(f"test track resolved on TIDAL: {_format_track_line(track)}")
            except Exception as error:
                report.fail(f"unable to resolve test track on TIDAL: {error}")
        if track is None:
            return report.finish()

        pre_existing = {}
        if library is not None:
            try:
                for row in library.file_details_for_tidal_id(TEST_TRACK_ID):
                    pre_existing[
                        (Path(row[7]).expanduser() / row[4]).resolve()
                    ] = row
            except Exception as error:
                report.fail(f"unable to query database for test track: {error}")

        files_to_check = []
        newly_downloaded = False
        if pre_existing:
            report.info(
                "test track already available locally; verifying existing files"
            )
            files_to_check = sorted(pre_existing)
        else:
            try:
                result = self._downloader.by_track_url(
                    f"https://tidal.com/track/{TEST_TRACK_ID}", return_titles=True
                )
            except TidalSessionStaleError:
                report.fail("TIDAL session is stale; aborting test download")
                return report.finish()
            except Exception as error:
                report.fail(f"test download raised: {error}")
                return report.finish()
            if not result:
                report.fail("test download failed (see tidekeeper output above)")
                return report.finish()
            completed_files = [Path(file_path) for file_path in result[0]]
            files_to_check = completed_files
            newly_downloaded = bool(completed_files)
            if completed_files:
                report.ok(
                    f"test track downloaded ({', '.join(f.name for f in completed_files)})"
                )
            else:
                report.info("tidekeeper reported the track was already on disk (skip)")

        for file_path in files_to_check:
            if not file_path.is_file():
                report.fail(f"downloaded file is gone: {file_path}")
                continue
            size = file_path.stat().st_size
            if size == 0:
                report.fail(f"downloaded file is empty: {file_path}")
            else:
                report.ok(f"file on disk: {file_path.name} ({size} bytes)")
            tag_track_id = _read_track_id(file_path)
            if tag_track_id:
                report.ok(f"TRACK_ID tag present: {tag_track_id}")
            else:
                report.warn(f"no TRACK_ID tag in {file_path.name}")

        if library is not None:
            report.step("database entries for the test track")
            try:
                rows = library.file_details_for_tidal_id(TEST_TRACK_ID)
            except Exception as error:
                report.fail(f"unable to query the files table: {error}")
                rows = []
            if not rows:
                report.fail("no entry in the files table for the test track")
            for track_row_id, title, artist, _, path, filename, missing_at, root in rows:
                absolute = Path(root).expanduser() / path
                if missing_at:
                    report.fail(f"files row is marked missing: {path}")
                elif not absolute.is_file():
                    report.fail(f"files row points to a missing path: {path}")
                else:
                    report.ok(f"files row matches disk entry: {path}")
                tag_track_id = _read_track_id(absolute) if absolute.is_file() else None
                if tag_track_id and tag_track_id != track_row_id:
                    report.fail(
                        f"TRACK_ID tag ({tag_track_id}) does not match files.track_id "
                        f"({track_row_id}) for {filename}"
                    )
                elif tag_track_id:
                    report.ok("TRACK_ID tag matches the files table entry")
                report.ok(
                    f"tracks entry linked to tidal_id {TEST_TRACK_ID}: "
                    f"{title} - {artist} (track_id={track_row_id})"
                )

            if newly_downloaded:
                report.step("cleanup")
                for file_path in files_to_check:
                    try:
                        file_path.unlink(missing_ok=True)
                    except OSError as error:
                        report.warn(f"unable to remove test file {file_path}: {error}")
                try:
                    purged = library.purge_tidal_track(TEST_TRACK_ID)
                    report.ok(
                        f"test artifacts removed ({purged['files']} files row(s), "
                        f"track row {'removed' if purged['track_removed'] else 'kept'})"
                    )
                except Exception as error:
                    report.warn(f"unable to remove test db rows: {error}")

        return report.finish()

    def run_playlists_doctor(self):
        report = DoctorReport("playlists")
        names = self._selection_names()
        report.info(f"{len(names)} selected playlist(s), using the local database cache")
        if not names:
            report.warn("no playlists are selected (utils > manage selected playlist)")
            return report.finish()

        library = None
        try:
            library = self._get_library()
        except Exception as error:
            report.fail(f"database unavailable: {error}")
        if library is None:
            report.fail("local database is disabled or unavailable")
            return report.finish()

        unsynced = 0
        totals = {"missing_in_db": 0, "unresolved_tidal_id": 0, "missing_files": 0}
        for name in sorted(names, key=str.casefold):
            try:
                audit = library.audit_playlist(name)
            except Exception as error:
                report.fail(f"{name}: audit failed ({error})")
                continue
            if not audit["synced"]:
                unsynced += 1
                report.warn(
                    f"{name}: not in database (run 'watch playlist files' "
                    f"or the missing tracks doctor)"
                )
                continue
            total = audit["total"] or 0
            membership = audit["membership"]
            matched = audit["matched"]
            unresolved = audit["missing_tidal_id"]
            no_files = audit["missing_files"]
            # Coverage is the number of TIDAL playlist ids matched to the
            # library, not the number of distinct local files: a single file
            # can cover several playlist entries (duplicate versions).
            coverage = matched if matched is not None else membership
            missing_in_db = max(0, total - coverage)
            totals["missing_in_db"] += missing_in_db
            totals["unresolved_tidal_id"] += len(unresolved)
            totals["missing_files"] += len(no_files)
            line = (
                f"{name}: {coverage} covered of {total}, "
                f"{missing_in_db} missing in db"
            )
            if unresolved:
                line += f", {len(unresolved)} without tidal_id"
            if no_files:
                line += f", {len(no_files)} file missing"
            if missing_in_db or unresolved or no_files:
                report.warn(line)
            else:
                report.ok(line)
            for _, title, artist in unresolved:
                report.info(f"  no tidal_id: {title} - {artist}")
            for _, title, artist in no_files:
                report.info(f"  file missing: {title} - {artist}")

        report.step("summary")
        report.info(f"playlists not synced to db: {unsynced}")
        report.info(f"total missing in db: {totals['missing_in_db']}")
        report.info(f"total tracks without tidal_id: {totals['unresolved_tidal_id']}")
        report.info(f"total tracks with missing file: {totals['missing_files']}")
        if totals["missing_in_db"]:
            report.info(
                "run the missing tracks doctor to resolve and download these tracks"
            )
        return report.finish()

    def run_missing_tracks_doctor(self, confirm=True):
        from InquirerPy import prompt as inquirer_prompt

        report = DoctorReport("missing tracks")
        td_session = (self._model.sessions or {}).get("td")
        if td_session is None:
            report.fail("no TIDAL session available")
            return report.finish()
        library = None
        try:
            library = self._get_library()
        except Exception as error:
            report.fail(f"database unavailable: {error}")
        if library is None:
            report.fail("local database is disabled or unavailable")
            return report.finish()

        names = self._selection_names()
        report.info(f"checking {len(names)} selected playlist(s) against TIDAL")
        if not names:
            report.warn("no playlists are selected (utils > manage selected playlist)")
            return report.finish()

        try:
            td_playlists = get_td_playlists_wrapper(td_session)
        except Exception as error:
            report.fail(f"unable to fetch TIDAL playlists: {error}")
            return report.finish()

        missing = []
        for name in tqdm(sorted(names, key=str.casefold),
                         desc=t.busy("analyzing playlists"), unit="playlist"):
            playlist = td_playlists.get(name)
            if playlist is None:
                report.warn(f"{name}: not found among your TIDAL playlists")
                continue
            try:
                tracks = asyncio.run(
                    get_all_playlist_tracks(
                        playlist, show_log=False, show_progress=False
                    )
                )
            except Exception as error:
                report.fail(f"{name}: unable to fetch tracks ({error})")
                continue
            try:
                match_map = library.available_track_id_map(tracks)
            except Exception as error:
                report.fail(f"{name}: unable to match against the db ({error})")
                continue
            missing_tracks = [
                track for track in tracks if str(track.id) not in match_map
            ]
            # Keep the cached membership used by the playlists doctor accurate,
            # so tracks downloaded after the last 'watch playlist files' run
            # (by this doctor or a concurrent instance) stop showing up as
            # "missing in db" until the next explicit refresh. Coverage counts
            # playlist entries, not unique ids (a duplicated track must not
            # count as a missing entry).
            try:
                library.save_playlist_membership(
                    name, str(playlist.id), len(tracks), match_map.values(),
                    matched_tracks=len(tracks) - len(missing_tracks),
                )
            except Exception:
                pass
            if missing_tracks:
                report.warn(
                    f"{name}: {len(missing_tracks)} of {len(tracks)} track(s) missing"
                )
                for track in missing_tracks:
                    report.info(f"  missing: {_format_track_line(track)}")
                    missing.append((name, track))
            else:
                report.ok(f"{name}: complete ({len(tracks)} tracks)")

        report.step("analysis")
        unique_tracks = {}
        for playlist_name, track in missing:
            entry = unique_tracks.setdefault(str(track.id), {"track": track, "playlists": []})
            entry["playlists"].append(playlist_name)
        report.info(
            f"total missing tracks across selection: {len(missing)} "
            f"({len(unique_tracks)} unique)"
        )
        if not unique_tracks:
            return report.finish()

        if confirm:
            answer = inquirer_prompt([{
                "type": "confirm",
                "name": "confirm",
                "message": f"attempt to download {len(unique_tracks)} missing track(s)?",
                "default": False,
            }])
            if not answer.get("confirm"):
                report.info("download attempts cancelled")
                return report.finish()

        def indexed_files_rows(tidal_id):
            try:
                return [
                    row for row in library.file_details_for_tidal_id(tidal_id)
                    if not row[6]
                    and (Path(row[7]).expanduser() / row[4]).is_file()
                ]
            except Exception:
                return []

        downloaded = 0
        failures = []
        not_found = []
        for tidal_id, entry in tqdm(
            unique_tracks.items(), desc=t.busy("downloading missing tracks"), unit="track"
        ):
            track = entry["track"]
            label = f"{_format_track_line(track)} ({', '.join(entry['playlists'])})"
            # A concurrent instance (watcher/other download) may have already
            # indexed the track since the analysis pass.
            if indexed_files_rows(tidal_id):
                downloaded += 1
                report.info(f"already available, skipping: {label}")
                continue
            try:
                result = self._downloader.by_track_url(
                    f"https://tidal.com/track/{track.id}", return_titles=True
                )
            except TidalSessionStaleError:
                report.fail("TIDAL session is stale; aborting downloads")
                break
            except Exception as error:
                failures.append((label, f"download error: {error}"))
                continue
            if not result:
                # tidekeeper reported a failure, but the file may still be on
                # disk and indexed (e.g. matched by a concurrent importer).
                if indexed_files_rows(tidal_id):
                    downloaded += 1
                    report.info(f"tidekeeper failed but track is already indexed: {label}")
                elif not self._track_exists_on_tidal(td_session, tidal_id):
                    not_found.append((label, track))
                else:
                    failures.append((label, "tidekeeper download failed"))
                continue
            healthy = indexed_files_rows(tidal_id)
            if not healthy:
                try:
                    rows = library.file_details_for_tidal_id(tidal_id)
                except Exception as error:
                    failures.append((label, f"db verification error: {error}"))
                    continue
                if rows:
                    failures.append((label, "indexed but marked missing in the db"))
                else:
                    failures.append(
                        (label, "no files table entry after download (import failed)")
                    )
                continue
            track_row_id = healthy[0][0]
            tag_track_id = _read_track_id(Path(healthy[0][7]).expanduser() / healthy[0][4])
            if tag_track_id and tag_track_id != track_row_id:
                failures.append(
                    (label, f"TRACK_ID tag {tag_track_id} != track_id {track_row_id}")
                )
                continue
            downloaded += 1

        report.step("download results")
        report.info(
            f"successfully downloaded and indexed: {downloaded}/{len(unique_tracks)}"
        )
        if not_found:
            report.warn(f"tracks not found/available on TIDAL: {len(not_found)}")
            for label, _ in not_found:
                report.info(f"  unavailable: {label}")
        for label, reason in failures:
            report.fail(f"{label}: {reason}")

        if not_found and confirm:
            answer = inquirer_prompt([{
                "type": "confirm",
                "name": "confirm",
                "message": f"do you want to manually search these {len(not_found)} track(s)?",
                "default": True,
            }])
            if answer.get("confirm"):
                resolved = 0
                for label, track in not_found:
                    status, detail = self._manual_search_track(
                        td_session, library, label, track, indexed_files_rows
                    )
                    if status == "resolved":
                        resolved += 1
                        downloaded += 1
                        report.ok(f"manually resolved: {label} -> {detail}")
                    elif status == "skipped":
                        report.info(f"skipped: {label}")
                    else:
                        report.fail(f"manual search failed: {label}: {detail}")
                report.info(
                    f"manually resolved {resolved}/{len(not_found)} "
                    f"unavailable track(s)"
                )
            else:
                report.info("manual search skipped")

        return report.finish()

    def _track_exists_on_tidal(self, td_session, tidal_id):
        try:
            return bool(td_session.track(str(tidal_id)))
        except Exception:
            return False

    def _manual_search_track(self, td_session, library, label, track, indexed_files_rows):
        from InquirerPy import prompt as inquirer_prompt

        query = (
            f"{track.name} "
            f"{getattr(getattr(track, 'artist', None), 'name', '')}"
        ).strip()
        try:
            results = td_session.search(query, models=[tidalapi.media.Track])
        except Exception as error:
            return "failed", f"search error: {error}"
        candidates = (results or {}).get("tracks") or []
        if not candidates:
            return "failed", f"no search results for '{query}'"

        def duration(candidate):
            seconds = getattr(candidate, "duration", None)
            return f" ({seconds // 60}:{seconds % 60:02d})" if seconds else ""

        choice_lines = [
            f"{_format_track_line(candidate)}{duration(candidate)} "
            f"[tidal id {candidate.id}]"
            for candidate in candidates[:15]
        ]
        choice_lines.append("skip this track")
        answer = inquirer_prompt([{
            "type": "list",
            "name": "choice",
            "message": f"choose a TIDAL match for '{label}':",
            "choices": choice_lines,
        }])
        chosen = answer.get("choice")
        if chosen is None or chosen == "skip this track":
            return "skipped", None
        candidate = candidates[choice_lines.index(chosen)]
        candidate_id = str(candidate.id)
        if candidate_id == str(track.id):
            return "failed", "selected track is the same unavailable id"

        try:
            result = self._downloader.by_track_url(
                f"https://tidal.com/track/{candidate_id}", return_titles=True
            )
        except TidalSessionStaleError:
            return "failed", "TIDAL session is stale"
        except Exception as error:
            return "failed", f"download error: {error}"
        rows = indexed_files_rows(candidate_id)
        if not rows:
            return "failed", (
                "selected match did not produce an indexed file"
                + ("" if result else " (download failed)")
            )
        try:
            # The playlist still references the removed track id; repoint the
            # local file's track record to it so future runs treat it as the
            # official substitute instead of reporting it missing forever.
            library.set_tidal_id(rows[0][0], track.id)
        except Exception as error:
            return "failed", f"downloaded but could not relink track row: {error}"
        return "resolved", f"{_format_track_line(candidate)} [tidal id {candidate_id}]"

    def run_mp3_quality_doctor(self):
        report = DoctorReport("mp3 quality")
        if not shutil.which("ffprobe"):
            report.fail(
                "ffprobe not found; install ffmpeg (includes ffprobe) to check mp3 quality"
            )
            return report.finish()

        flac_dir = Path(self._settings.get_flac_dir())
        mp3_dir = Path(self._settings.get_mp3_dir())
        if not mp3_dir.is_dir():
            report.fail(f"mp3 directory not found: {mp3_dir}")
            return report.finish()

        report.step("scanning mp3 files")
        mp3_files = sorted(
            path for path in mp3_dir.rglob("*.mp3")
            if not path.name.startswith("._")
        )
        report.info(f"{len(mp3_files)} mp3 file(s) found under {mp3_dir}")
        if not mp3_files:
            return report.finish()

        checked = 0
        for mp3_file in tqdm(
            mp3_files, desc=t.busy("checking mp3 quality"), unit="file"
        ):
            relative = mp3_file.relative_to(mp3_dir)
            flac_file = flac_dir / relative.with_suffix(".flac")

            info, error = _ffprobe_stream_info(mp3_file)
            if info is None:
                report.fail(f"{relative}: unreadable/corrupted ({error})")
                continue
            checked += 1

            bit_rate = info["bit_rate"]
            if bit_rate is None:
                report.warn(f"{relative}: could not determine bitrate")
            elif abs(bit_rate - MP3_TARGET_BITRATE) > MP3_BITRATE_TOLERANCE:
                report.warn(
                    f"{relative}: bitrate {bit_rate // 1000}kbps deviates "
                    f"from expected 320kbps"
                )
            else:
                report.ok(f"{relative}: bitrate {bit_rate // 1000}kbps")

            if not flac_file.is_file():
                report.warn(f"{relative}: no matching source flac at {flac_file}")
                continue

            flac_info, flac_error = _ffprobe_stream_info(flac_file)
            if (
                flac_info is None
                or flac_info["duration"] is None
                or info["duration"] is None
            ):
                report.warn(
                    f"{relative}: unable to compare duration against source "
                    f"flac ({flac_error or 'no duration'})"
                )
                continue
            drift = abs(flac_info["duration"] - info["duration"])
            if drift > MP3_DURATION_TOLERANCE:
                report.fail(
                    f"{relative}: duration mismatch vs flac "
                    f"({info['duration']:.1f}s vs {flac_info['duration']:.1f}s)"
                )
            else:
                report.ok(
                    f"{relative}: duration matches source flac "
                    f"({info['duration']:.1f}s)"
                )

        report.step("summary")
        report.info(f"{checked}/{len(mp3_files)} file(s) readable by ffprobe")
        return report.finish()

    def run_all(self):
        results = []
        for runner in (
            self.run_download_doctor,
            self.run_playlists_doctor,
            self.run_missing_tracks_doctor,
            self.run_mp3_quality_doctor,
        ):
            results.append(runner())
        return all(results)
