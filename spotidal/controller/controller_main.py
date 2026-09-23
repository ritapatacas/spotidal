import asyncio
import os
import re
import threading
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import tidalapi
from tqdm import tqdm
from spotidal.model import Model
from ..model.helpers.type import PlaylistReference as playlist
import spotidal.view.view as view

from ..model.settings import Settings
from ..model.sync import Sync
from ..model.download import Download
from ..model.doctor import Doctor
from ..model.genre import GenreFiller
from ..model.flac_to_mp3 import FlacToMp3
from ..model.normalize_audio import NormalizeToFlac
from ..model.library import MusicLibrary
from ..model.rekordbox import RekordboxExport, RekordboxImport
from ..webui.server import run_server as run_search_server
from ..model.library_watcher import LibraryWatcher
from ..model.helpers.sync.playlists_handler import get_td_playlists_wrapper, get_tracks_from_sp_playlist
from ..model.helpers.tidalapi import get_all_playlist_tracks
from ..model.helpers.type.file import Files
from ..model.helpers.td_downloader import (
    TidalSessionStaleError,
    check_login,
    clean_tmp,
)
from ..view.text import Text as t


def _normalize_for_match(text):
    text = re.sub(r"\(feat[^)]*\)", "", text or "", flags=re.IGNORECASE)
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.casefold().split())


def _strip_version_suffix(text):
    # "Song - Remastered 2011" / "Song (Radio Mix)" / "Song [Live]" all
    # describe the same underlying song as plain "Song" — cut everything
    # from the first " - ", "(" or "[" so version/remaster/edit labels
    # don't register as a title or album mismatch.
    text = re.sub(r"\s*[-–].*$", "", text or "")
    text = re.sub(r"\s*[\(\[].*$", "", text)
    return text.strip()


def _strip_diacritics(text):
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _format_track(candidate):
    artists = ", ".join(a.name for a in (getattr(candidate, "artists", None) or []))
    name = getattr(candidate, "full_name", None) or candidate.name
    return f"{name} — {artists}" if artists else name


def _split_artists(text):
    parts = re.split(r",|&|/| feat\.| ft\.| x | and ", text or "", flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


class ControllerMain:
    def __init__(self, model: Model):
        self.model = model
        self._settings = Settings()
        self._library = None
        self._library_error = None
        self._startup_warnings = []
        if self._settings.get_database_enabled():
            try:
                self._library = MusicLibrary(
                    self._settings.get_download_dir(), self._settings.get_database_path()
                )
                # Do not block the first menu while scanning the whole library.
                threading.Thread(
                    target=self._library.reconcile_all,
                    daemon=True,
                ).start()
            except Exception as error:
                self._library_error = error
                self._startup_warnings.append(
                    "local directory unavailable; db features are disabled"
                )
        self._library_watcher = None
        if (
            self._library
            and self._settings.get_database_enabled()
            and self._settings.get_watcher_enabled()
        ):
            try:
                self._library_watcher = LibraryWatcher(self._library)
                self._library_watcher.start()
            except Exception as error:
                self._library_watcher = None
                self._startup_warnings.append(
                    f"unable to start local library monitor: {error}"
                )
        self._sync = Sync(self.model.sessions)
        self._download = Download(self.model.sessions)
        self._doctor = Doctor(self.model, self._settings, self._download)

    def get_startup_warnings(self):
        return self._startup_warnings

    def _playlist_info(self, reference):
        info = playlist.get_info(reference)
        if info is None:
            self.model.get_parsed_playlists()
            info = playlist.get_info(reference)
        return info

    def _require_local_directory(self, path=None, settings_area="Download settings"):
        path = Path(path or self._settings.get_download_dir()).expanduser()
        candidate = path
        # Callers pass both directories (download/flac/mp3) and file paths
        # (the database .db itself); validate the containing directory either
        # way, and tolerate partially-created paths by falling back to the
        # closest existing ancestor like before.
        if candidate.is_file():
            candidate = candidate.parent
        while not candidate.is_dir() and candidate != candidate.parent:
            candidate = candidate.parent
        if not candidate.is_dir() or not os.access(candidate, os.W_OK):
            print(t.warning(
                "local directory is unavailable; configure it in "
                f"{t.b('Settings')} > {t.b(settings_area)}"
            ))
            return False
        return True

    def sync(self, e):
        for p in e if isinstance(e, list) else [e]:
            info = self._start_playlist_job(p)
            if info and info.get("sp_id"):
                self._sync.by_sp_id(info["sp_id"])
            else:
                print(t.warning(
                    f"skipping '{str(p)}': no matching spotify playlist id"
                ))

    def _start_playlist_job(self, reference):
        info = self._playlist_info(reference)
        name = info["name"] if info else str(reference)
        print("\n" + t.log(f"playlist '{name}'"))
        return info

    def sync_url(self, url):
        parsed = urlparse(url.strip())
        parts = [part for part in parsed.path.split("/") if part]
        if (
            not parsed.netloc.lower().endswith("open.spotify.com")
            or len(parts) < 2
            or parts[0] != "playlist"
        ):
            raise ValueError("sync URL must be a Spotify playlist URL")
        self._sync.by_sp_id(parts[1])

    def download(self, e):
        if not self._require_local_directory():
            return
        if isinstance(e, list):
            playlist_ids = []
            for p in e:
                info = self._playlist_info(p)
                if info and info.get("td_id"):
                    playlist_ids.append(info["td_id"])
            if playlist_ids:
                try:
                    if len(playlist_ids) == 1:
                        self._download.by_td_id(playlist_ids[0])
                    else:
                        self._download.by_td_ids(playlist_ids)
                except TidalSessionStaleError:
                    raise
                except Exception as error:
                    print(t.error(f"unable to download playlists {t.grey(str(error))}"))
        else:
            info = self._playlist_info(e)
            if info and info.get("td_id"):
                try:
                    self._download.by_td_id(info["td_id"])
                except TidalSessionStaleError:
                    raise
                except Exception as error:
                    print(t.error(
                        f"unable to download playlist '{info['name']}' "
                        f"{t.grey(str(error))}"
                    ))

    def download_url(self, url):
        if not self._require_local_directory():
            return
        self._download.by_url(url)

    def get_download_dir(self):
        return self._settings.get_download_dir()

    def get_notify_sound_delay(self):
        return self._settings.get_notify_sound_delay()

    def set_notify_sound_delay(self, minutes):
        return self._settings.set_option("notifySoundAfterMinutes", minutes)

    def refresh_td_session(self):
        refreshed = self.model.refresh_td_session()
        if refreshed:
            self._download.td_session = self.model.sessions["td"]
        return refreshed

    def flac_to_mp3(self):
        if not self._require_local_directory() or not self._require_local_directory(
            self._settings.get_database_path()
        ):
            return
        FlacToMp3(
            self._settings.get_download_dir(),
            self._settings.get_flac_dir(),
            self._settings.get_mp3_dir(),
            self._settings.get_database_path(),
        ).convert()

    def normalize_to_flac(self):
        if not self._require_local_directory() or not self._require_local_directory(
            self._settings.get_database_path()
        ):
            return
        NormalizeToFlac(
            self._settings.get_download_dir(),
            self._settings.get_flac_dir(),
            self._settings.get_database_path(),
        ).convert()

    def reconcile_library(self):
        if not self._settings.get_database_enabled():
            print(t.error("database is disabled"))
            return
        if not self._library:
            self._require_local_directory(
                self._settings.get_database_path(), "Database settings"
            )
            return
        with tqdm(desc=t.busy("scanning local files"), unit="file") as progress:
            changes = self._library.reconcile_all(on_progress=progress.update)
        print(t.log(
            "database updated "
            f"({changes['added']} added, "
            f"{changes['restored']} restored, "
            f"{changes['missing']} marked missing)"
        ))

    def fill_missing_database_data(self):
        if not self._settings.get_database_enabled():
            print(t.error("database is disabled"))
            return
        if not self._library or not self.model.sessions:
            print(t.error("TIDAL session or local database is unavailable"))
            return
        purged_orphans = self._library.purge_orphan_tracks()
        if purged_orphans:
            print(t.log(
                f"removed {purged_orphans} orphaned track record(s) with no local file"
            ))
        repair_stats = self._library.repair_unknown_artists()
        if repair_stats["total_unknown"]:
            print(t.log(
                f"unknown artist: {repair_stats['total_unknown']} track(s) total, "
                f"{repair_stats['with_files']} with a local file, "
                f"{repair_stats['repaired']} repaired from filename"
            ))
            for sample in repair_stats["unparsed_samples"]:
                print(t.log_grey(f"unparsed filename: {sample!r}"))
        tracks = self._library.tracks_missing_tidal_id()
        if not tracks:
            print(t.log("database already has all TIDAL track IDs"))
            return
        tidal_session = self.model.sessions["td"]
        filled = 0
        errors = 0
        ambiguous = 0
        error_samples = []
        debug_samples = []
        for track_id, title, artist, album in tqdm(
            tracks, desc=t.busy("fixing missing database data"), unit="track"
        ):
            try:
                results = tidal_session.search(
                    f"{title} {artist}", models=[tidalapi.media.Track]
                )
            except Exception as error:
                errors += 1
                if len(error_samples) < 3:
                    error_samples.append(f"{type(error).__name__}: {error}")
                continue
            normalized_title = _normalize_for_match(title)
            all_tracks = results.get("tracks", [])
            candidates = [
                candidate for candidate in all_tracks
                if normalized_title in {
                    _normalize_for_match(candidate.name),
                    _normalize_for_match(getattr(candidate, "full_name", None) or ""),
                }
            ]
            if album:
                normalized_album = _normalize_for_match(album)
                album_matches = [
                    candidate for candidate in candidates
                    if _normalize_for_match(
                        getattr(getattr(candidate, "album", None), "name", "")
                    ) == normalized_album
                ]
                candidates = album_matches or candidates
            if len(candidates) > 1 and artist:
                # Local `artist` can be a "A, B" joined string (multi-artist
                # tracks); compare each individually against tidal's artist list.
                local_artists = {
                    _normalize_for_match(name) for name in _split_artists(artist)
                }
                artist_matches = [
                    candidate for candidate in candidates
                    if local_artists & {
                        _normalize_for_match(getattr(a, "name", ""))
                        for a in (getattr(candidate, "artists", None) or [])
                    }
                ]
                candidates = artist_matches or candidates
            if len(candidates) == 1:
                try:
                    self._library.set_tidal_id(track_id, candidates[0].id)
                    filled += 1
                except Exception as error:
                    errors += 1
                    if len(error_samples) < 3:
                        error_samples.append(f"{type(error).__name__}: {error}")
            else:
                ambiguous += 1
                if len(debug_samples) < 5:
                    local_line = f"{title} — {artist}" + (f" [{album}]" if album else "")
                    candidate_lines = [
                        f"    {_format_track(c)}" for c in (candidates or all_tracks)[:5]
                    ]
                    debug_samples.append(
                        f"  missing: {local_line}\n" + "\n".join(candidate_lines)
                    )

        summary = (
            f"filled {filled}/{len(tracks)} missing TIDAL track ID(s) "
            f"({ambiguous} no unique match, {errors} search/write error(s))"
        )
        print(t.log(summary))
        for sample in error_samples:
            print(t.warning(f"sample error: {sample}"))
        for sample in debug_samples:
            print(t.log_grey(sample))

    def audit_playlist_consistency(self, names):
        if not self._library:
            print(t.error("local database is unavailable"))
            return
        sp_session = self.model.sessions["sp"]
        td_session = self.model.sessions["td"]
        checked = flagged = not_found = 0
        for name in names:
            sp_id = self._library.get_playlist_spotify_id(name)
            if not sp_id:
                print(t.warning(f"skipping '{name}': no matching spotify playlist id"))
                continue
            tracks = asyncio.run(
                get_tracks_from_sp_playlist(sp_session, {"id": sp_id, "name": name})
            )
            for track in tqdm(tracks, desc=t.busy(f"auditing '{name}'"), unit="track"):
                title = track.get("name")
                artists = [a["name"] for a in track.get("artists", [])]
                artist = ", ".join(artists)
                album = (track.get("album") or {}).get("name")
                isrc = (track.get("external_ids") or {}).get("isrc")

                local = self._library.find_track_by_isrc(isrc)
                if not local:
                    not_found += 1
                    continue
                checked += 1

                def _clean(text):
                    return _normalize_for_match(_strip_diacritics(_strip_version_suffix(text)))

                mismatches = []
                if _clean(local["title"]) != _clean(title):
                    mismatches.append(f"title mismatch (db={local['title']!r} vs spotify={title!r})")
                local_artists = {
                    _normalize_for_match(_strip_diacritics(a))
                    for name in [local["artist"] or ""]
                    for a in _split_artists(name)
                }
                sp_artists = {
                    _normalize_for_match(_strip_diacritics(a))
                    for name in artists
                    for a in _split_artists(name)
                }
                if local_artists and sp_artists and not (local_artists & sp_artists):
                    mismatches.append(f"artist mismatch (db={local['artist']!r} vs spotify={artist!r})")
                if local["album"] and album and _clean(local["album"]) != _clean(album):
                    mismatches.append(f"album mismatch (db={local['album']!r} vs spotify={album!r})")

                try:
                    # Only an exact ISRC match on the TIDAL candidate is
                    # trusted enough to propose a tidal_id correction — a
                    # title/artist/duration fallback still misfires often
                    # in practice (same-titled cover, remix, or same-length
                    # unrelated song by a different artist), so a track
                    # whose TIDAL copy doesn't carry a matching ISRC is left
                    # unflagged here rather than risk a wrong "fix".
                    results = td_session.search(f"{title} {artist}", models=[tidalapi.media.Track])
                    candidates = results.get("tracks", [])
                    found = next((c for c in candidates if getattr(c, "isrc", None) == isrc), None)
                    if found and local["tidal_id"] and str(found.id) != str(local["tidal_id"]):
                        mismatches.append(f"tidal_id mismatch (db={local['tidal_id']} vs found={found.id})")
                except Exception:
                    pass

                self._library.set_review(local["track_id"], "; ".join(mismatches) if mismatches else None)
                if mismatches:
                    flagged += 1
        print(t.log(
            f"audit complete: {checked} checked, {flagged} flagged for review, "
            f"{not_found} not found locally (isrc lookup failed)"
        ))

    def resolve_playlist_name_from_url(self, url):
        parsed = urlparse(url.strip())
        host = parsed.netloc.lower()
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2 or parts[0] != "playlist":
            raise ValueError("URL must be a TIDAL or Spotify playlist URL")
        media_id = parts[1]
        if host.endswith("tidal.com"):
            playlist = self.model.sessions["td"].playlist(media_id)
            if not playlist:
                raise ValueError("TIDAL playlist not found")
            return playlist.name
        if host.endswith("open.spotify.com"):
            playlist = self.model.sessions["sp"].playlist(media_id)
            return playlist["name"]
        raise ValueError("unsupported TIDAL or Spotify URL")

    def filter_playlists_with_missing(self, selection):
        if not self._settings.get_database_enabled():
            return set(selection)
        stats = self.get_selection_stats(selection)
        return {item["name"] for item in stats if item["missing"] > 0}

    def get_selection_stats(self, selection, force_refresh=False):
        # Build a fresh MusicLibrary the same way Downloader._prepare_tracks does,
        # so "missing" here matches what the real download would skip.
        settings = Files.SETTINGS.load() or {}
        try:
            library = MusicLibrary(
                settings.get("downloadPath", "~/Spotidal"),
                settings.get("databaseLocation"),
            )
        except Exception:
            library = None

        td_playlists = None
        stats = []
        for name in tqdm(
            sorted(selection), desc=t.busy("fetching playlists"), unit="playlist"
        ):
            if force_refresh and library:
                library.clear_playlist_tracks(name)
            cached = (
                library.get_playlist_track_stats(name)
                if library and not force_refresh
                else None
            )
            if cached is not None:
                stats.append({"name": name, **cached})
                continue

            if td_playlists is None:
                td_playlists = get_td_playlists_wrapper(self.model.sessions["td"])
            td_playlist = td_playlists.get(name)
            if td_playlist is None:
                stats.append({"name": name, "total": 0, "local": 0, "missing": 0})
                continue
            tracks = asyncio.run(
                get_all_playlist_tracks(td_playlist, show_log=False, show_progress=False)
            )
            total = len(tracks)
            try:
                match_map = library.available_track_id_map(tracks) if library else {}
            except Exception:
                match_map = {}
            # Coverage is per TIDAL playlist id (match_map keys), not per
            # distinct local file: one file can cover several playlist
            # entries (duplicate versions share a row), and the download
            # pipeline skips every id already present in match_map — counting
            # distinct files instead reported those covered ids as
            # permanently "missing". Counted per entry, so a track listed
            # twice in the playlist is not counted as missing when the
            # (single) id is covered.
            local = sum(1 for track in tracks if str(track.id) in match_map)
            stats.append({
                "name": name,
                "total": total,
                "local": local,
                "missing": total - local,
            })
            if library:
                try:
                    library.save_playlist_membership(
                        name, str(td_playlist.id), total, match_map.values(),
                        matched_tracks=local,
                    )
                except Exception:
                    pass
        return stats

    def stop_library_monitoring(self):
        if self._library_watcher:
            self._library_watcher.stop()

    def clean_tmp(self):
        if not self._require_local_directory():
            return
        removed_parts = clean_tmp(self._settings.get_download_dir())
        message = f"temporary download files cleaned ({removed_parts} parts folder(s) deleted)"
        if self._library:
            purged = self._library.purge_temp_artifacts()
            if purged["files"]:
                message += (
                    f", {purged['files']} orphaned tmp track(s) purged from database"
                    f" ({purged['tracks']} track record(s) removed)"
                )
        print(t.log(message))

    def tidekeeper_doctor(self):
        check_login()

    def doctor_download(self):
        return self._doctor.run_download_doctor()

    def doctor_playlists(self):
        return self._doctor.run_playlists_doctor()

    def doctor_missing_tracks(self):
        from ..view.prompt import MissingTracksModeMenu

        action = view.missing_tracks_mode_menu()
        modes = {
            MissingTracksModeMenu.DOWNLOAD: "download",
            MissingTracksModeMenu.FIND: "find",
            MissingTracksModeMenu.FIND_AND_DOWNLOAD: "find_and_download",
        }
        mode = modes.get(action)
        if mode is None:
            return None
        # Choosing "download current missing tracks" from the menu is
        # itself the confirmation; don't ask a second time.
        confirm = mode != "download"
        return self._doctor.run_missing_tracks_doctor(mode=mode, confirm=confirm)

    def download_current_missing_tracks(self):
        # Shortcut for the "download current missing tracks" menu entry:
        # skips the mode-selection submenu and the confirm prompt, since
        # picking this entry directly is already the confirmation.
        return self._doctor.run_missing_tracks_doctor(mode="download", confirm=False)

    def doctor_mp3_quality(self):
        return self._doctor.run_mp3_quality_doctor()

    def doctor_all(self):
        return self._doctor.run_all()

    def fill_genres(self, track_ids=None):
        if not self._settings.get_database_enabled():
            print(t.error("database is disabled"))
            return
        if not self._library:
            self._require_local_directory(
                self._settings.get_database_path(), "Database settings"
            )
            return
        GenreFiller(self._library).run(track_ids=track_ids)

    def _require_genre_library(self):
        if not self._settings.get_database_enabled():
            print(t.error("database is disabled"))
            return None
        if not self._library:
            self._require_local_directory(
                self._settings.get_database_path(), "Database settings"
            )
            return None
        return self._library

    def final_genres(self):
        library = self._require_genre_library()
        return library.final_genres() if library else []

    def final_genre_styles(self, genre_name=None):
        library = self._require_genre_library()
        return library.final_genre_styles(genre_name) if library else []

    def add_final_genre(self, name):
        library = self._require_genre_library()
        if not library:
            return None, False
        genre_id, created = library.add_final_genre(name)
        if genre_id is not None and not created:
            print(t.log(f"genre '{name.strip()}' already exists"))
        return genre_id, created

    def add_style(self, name):
        library = self._require_genre_library()
        if not library:
            return None, False
        style_id, created = library.add_style(name)
        if style_id is not None and not created:
            print(t.log(f"style '{name.strip()}' already exists"))
        return style_id, created

    def playlist_names(self):
        library = self._require_genre_library()
        return library.playlist_names() if library else []

    def track_ids_for_playlists(self, names):
        library = self._require_genre_library()
        return library.track_ids_for_playlists(names) if library else []

    def export_rekordbox(self):
        if not self._settings.get_database_enabled():
            print(t.error("database is disabled"))
            return
        if not self._library:
            self._require_local_directory(
                self._settings.get_database_path(), "Database settings"
            )
            return
        export = RekordboxExport(
            self._library.database_path, self._library.root_path
        )
        output = self._library.root_path / "rekordbox"
        playlists = export.export_m3u8(output / "playlists")
        xml = export.export_xml(output / "rekordbox.xml")
        print(t.log(
            f"exported {xml['playlists']} playlists / {xml['tracks']} tracks"
            f" to {output}"
        ))
        if xml["skipped"]:
            print(t.warning(
                "skipped (no local mp3): " + ", ".join(xml["skipped"])
            ))
        print(t.log(
            "rekordbox: Preferences > Advanced > Database > rekordbox xml,"
            " point it at rekordbox.xml, then drag the Spotidal folder into"
            " your playlists"
        ))
        return {"m3u8": len(playlists["written"]), **xml}

    def import_rekordbox_metadata(self):
        if not self._settings.get_database_enabled():
            print(t.error("database is disabled"))
            return
        if not self._library:
            self._require_local_directory(
                self._settings.get_database_path(), "Database settings"
            )
            return
        try:
            source = RekordboxImport()
        except RuntimeError as error:
            print(t.error(str(error)))
            return
        result = self._library.import_rekordbox_metadata(source.tracks())
        print(t.log(
            f"bpm/key: matched {result['matched']} track(s), "
            f"{result['unmatched']} unmatched"
        ))
        return result

    def run_search_ui(self):
        if not self._settings.get_database_enabled():
            print(t.error("database is disabled"))
            return
        if not self._library:
            self._require_local_directory(
                self._settings.get_database_path(), "Database settings"
            )
            return
        run_search_server(self._library)

    def reset_sp_session(self):
        sp_credentials = view.setup_menu()
        self.model.setup_credentials(sp_credentials)
        self.model.open_sp_session()
    
    def change_download_dir(self):
        new_dir = view.download_dir_menu(self._settings.get_download_dir())
        if new_dir:
            saved = self._settings.set_download_dir(new_dir)
            print(t.log(f"download directory set to {saved}"))

    def change_download_quality(self):
        from ..model.settings import QUALITY_OPTIONS

        quality = view.download_quality_menu(
            QUALITY_OPTIONS, self._settings.get_download_quality()
        )
        if quality:
            self._settings.set_download_quality(quality)
            print(t.log(f"download quality set to {quality}"))

    def change_audio_quality(self):
        result = view.audio_quality_menu(
            self._settings.get_download_quality(),
            self._settings.get_quality_fallback(),
        )
        if result.get("target"):
            self._settings.set_download_quality(result["target"])
            self._settings.set_quality_fallback(result.get("fallback", "None"))

    def toggle_mp3_conversion(self):
        settings = self._settings.get_settings()
        value = view.toggle_menu(
            "automatic mp3 conversion", settings.get("autoConvertMp3", True)
        )
        if value:
            self._settings.set_option("autoConvertMp3", value == "enable")

    def change_database_option(self, action):
        settings = self._settings.get_settings()
        if action == "database enabled":
            value = view.toggle_menu("database", settings.get("databaseEnabled", True))
            if value:
                enabled = value == "enable"
                self._settings.set_option("databaseEnabled", enabled)
                if not enabled and self._library_watcher:
                    self._library_watcher.stop()
                    self._library_watcher = None
                elif enabled and not self._library:
                    self._require_local_directory(
                        self._settings.get_database_path(), "Database settings"
                    )
                elif enabled and not self._library_watcher and self._settings.get_watcher_enabled():
                    self._library_watcher = LibraryWatcher(self._library)
                    self._library_watcher.start()
        elif action == "run watcher (update database)":
            self.reconcile_library()
        elif action == "fill missing database data":
            self.fill_missing_database_data()
        elif action == "database location path":
            value = view.path_menu(self._settings.get_database_path(), "database location")
            if value:
                self._settings.set_option("databaseLocation", value)
                if not self._library and self._settings.get_database_enabled():
                    try:
                        self._library = MusicLibrary(
                            self._settings.get_download_dir(), value
                        )
                        print(t.log("local database initialized"))
                    except Exception as error:
                        print(t.warning(f"local directory is still unavailable: {error}"))
        elif action == "flac directory":
            value = view.path_menu(self._settings.get_flac_dir(), "flac directory")
            if value:
                self._settings.set_option("flacDirectory", value)
        elif action == "mp3 directory":
            value = view.path_menu(self._settings.get_mp3_dir(), "mp3 directory")
            if value:
                self._settings.set_option("mp3Directory", value)
        elif action == "other locations":
            print(t.log("other locations will be implemented later"))

    def reset_settings(self):
        self.reset_sp_session()
        self._settings.reset_settings()
        self._settings.check_tidal_login()


if __name__ == "__main__":
    controller = ControllerMain()
from urllib.parse import urlparse
