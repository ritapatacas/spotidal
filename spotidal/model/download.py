import asyncio
import sys
import time
from urllib.parse import urlparse

import tidalapi
from tqdm import tqdm

from .helpers import download
from .helpers.utils import list_handler
from .helpers.type.file import Files
from .helpers.sync.match import match
from .helpers.sync.playlists_handler import get_td_playlists_wrapper
from .helpers.sync.search import pick_td_playlist_for_sp_playlist
from .helpers.synchronizer import sync_playlists_wrapper
from .helpers.tidalapi import get_all_playlist_tracks
from .helpers.td_downloader import (
    TidalSessionStaleError,
    clean_tmp,
    login_tidekeeper,
    refresh_tidekeeper_token,
)
from .auth import save_td_session
from .library import MusicLibrary
from ..view.text import Text as t


DEFAULT_BATCH_SIZE = 50
# Fixed-width: the bar itself never changes size regardless of the current
# track name, which is shown on its own line below instead.
DOWNLOAD_BAR_FORMAT = (
    "{desc} \033[33m{percentage:4.1f}%\033[0m|{bar:75}|"
)


class DownloadProgress(tqdm):
    pass


def _format_duration(seconds):
    total_seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)
    return f"{minutes}m{remaining_seconds:02d}s"


class Download:
    def __init__(self, sessions):
        self.sp_session = sessions["sp"]
        self.td_session = sessions["td"]
        self.sp_credentials = Files.CREDENTIALS.load()["spotify"]
        self.batch_size = DEFAULT_BATCH_SIZE

    def _download_by_td_id(self, td_id):
        download(
            td_id,
            refresh_callback=self._refresh_td_token,
            reauth_callback=self._reauth_td_session,
        )

    def _refresh_td_token(self):
        credentials = refresh_tidekeeper_token()
        if credentials:
            self.td_session.access_token = credentials["access_token"]
            self.td_session.refresh_token = credentials["refresh_token"]
            save_td_session(self.td_session)
            return True
        if not self.td_session.refresh_token:
            return False
        refreshed = self.td_session.token_refresh(self.td_session.refresh_token)
        if refreshed:
            save_td_session(self.td_session)
        return refreshed

    def _reauth_td_session(self):
        try:
            credentials = login_tidekeeper()
        except Exception as error:
            print(t.error(f"TIDAL login failed: {error}"))
            return False
        self.td_session.access_token = credentials["access_token"]
        self.td_session.refresh_token = credentials["refresh_token"]
        save_td_session(self.td_session)
        return True

    def _reset_download_settings(self):
        self.batch_size = DEFAULT_BATCH_SIZE

    def _prepare_tracks(self, tracks):
        settings = Files.SETTINGS.load() or {}
        try:
            library = MusicLibrary(
                settings.get("downloadPath", "~/Spotidal"),
                settings.get("databaseLocation"),
            )
            available_ids = library.available_track_ids(tracks)
        except Exception:
            available_ids = set()
        pending = []
        skipped = []
        for track in tracks:
            if str(track.id) in available_ids:
                skipped.append(track)
            else:
                pending.append(track)
        return pending, skipped

    def _reconcile_downloaded_files(self):
        settings = Files.SETTINGS.load() or {}
        library = MusicLibrary(
            settings.get("downloadPath", "~/Spotidal"),
            settings.get("databaseLocation"),
        )
        library.reconcile_all()

    def by_td_id(self, td_id):
        self._reset_download_settings()
        playlist = self.td_session.playlist(td_id)
        tracks = asyncio.run(get_all_playlist_tracks(playlist, show_log=False))
        pending, skipped = self._prepare_tracks(tracks)
        self._download_tidal_playlist(
            playlist,
            pending,
            playlist_number=1,
            playlist_total=1,
            total_tracks=len(tracks),
            skipped_tracks=skipped,
        )
        self._reconcile_downloaded_files()

    def by_td_ids(self, td_ids):
        self._reset_download_settings()
        playlists = []
        for td_id in tqdm(
            td_ids, desc=t.busy("fetching playlists"), unit="playlist"
        ):
            playlist = self.td_session.playlist(td_id)
            tracks = asyncio.run(
                get_all_playlist_tracks(playlist, show_log=False, show_progress=False)
            )
            pending, skipped = self._prepare_tracks(tracks)
            playlists.append((playlist, pending, len(tracks), skipped))
        playlists.sort(key=lambda item: len(item[1]))

        total_tracks = sum(total for _, _, total, _ in playlists)
        skipped_total = sum(len(skipped) for _, _, _, skipped in playlists)
        pending_total = total_tracks - skipped_total
        print(
            "\n" + t.busy("playlists to download: ")
            + f"{len(playlists)} playlists, {total_tracks} tracks "
            + t.grey(f"({skipped_total} already available, {pending_total} to download)")
        )

        with DownloadProgress(
            total=pending_total,
            desc=t.busy("downloading:"),
            unit="track",
            ncols=120,
            bar_format=DOWNLOAD_BAR_FORMAT,
            file=sys.stdout,
        ) as progress:
            progress.downloaded_count = 0
            progress.download_total = pending_total
            overall = {
                "total_tracks": total_tracks,
                "skipped_total": skipped_total,
                "pending_total": pending_total,
            }
            for playlist_number, (playlist, tracks, total, skipped) in enumerate(playlists, 1):
                self._download_tidal_playlist(
                    playlist,
                    tracks,
                    playlist_number=playlist_number,
                    playlist_total=len(playlists),
                    progress=progress,
                    total_tracks=total,
                    skipped_tracks=skipped,
                    overall=overall,
                )
        self._reconcile_downloaded_files()

    def by_url(self, url):
        self._reset_download_settings()
        parsed = urlparse(url.strip())
        host = parsed.netloc.lower()
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("URL must contain a TIDAL or Spotify media type and ID")

        service = "spotify" if host.endswith("open.spotify.com") else "tidal" if host.endswith("tidal.com") else None
        if not service or parts[0] not in {"playlist", "album", "track"}:
            raise ValueError("unsupported TIDAL or Spotify URL")
        media_type, media_id = parts[:2]

        if service == "tidal":
            playlist = self.td_session.playlist(media_id) if media_type == "playlist" else None
            track = self.td_session.track(media_id) if media_type == "track" else None
            if playlist:
                tracks = asyncio.run(get_all_playlist_tracks(playlist, show_log=False))
                pending, skipped = self._prepare_tracks(tracks)
                self._download_tidal_playlist(
                    playlist,
                    pending,
                    playlist_number=1,
                    playlist_total=1,
                    total_tracks=len(tracks),
                    skipped_tracks=skipped,
                )
                self._reconcile_downloaded_files()
                MusicLibrary(Files.SETTINGS.load().get("downloadPath", "~/Spotidal")).associate_tidal_playlist(playlist, media_id)
            else:
                download(
                    url.strip(),
                    display_name=track.name if track else None,
                    refresh_callback=self._refresh_td_token,
                    reauth_callback=self._reauth_td_session,
                )
            return
        if media_type == "playlist":
            td_playlist = self._sync_playlist(media_id)
            if td_playlist is None:
                spotify_playlist = self.sp_session.playlist(media_id)
                td_playlist = get_td_playlists_wrapper(self.td_session).get(
                    spotify_playlist["name"]
                )
            if td_playlist is None:
                raise ValueError("Spotify playlist could not be converted to TIDAL")
            tracks = asyncio.run(get_all_playlist_tracks(td_playlist, show_log=False))
            pending, skipped = self._prepare_tracks(tracks)
            self._download_tidal_playlist(
                td_playlist,
                pending,
                playlist_number=1,
                playlist_total=1,
                total_tracks=len(tracks),
                skipped_tracks=skipped,
            )
            self._reconcile_downloaded_files()
            MusicLibrary(Files.SETTINGS.load().get("downloadPath", "~/Spotidal")).associate_tidal_playlist(td_playlist, str(td_playlist.id))
            return
        if media_type == "track":
            tracks = [self.sp_session.track(media_id)]
        else:
            tracks = self.sp_session.album_tracks(media_id)["items"]

        for spotify_track in tracks:
            if "external_ids" not in spotify_track:
                spotify_track = self.sp_session.track(spotify_track["id"])
            tidal_track = self._find_tidal_track(spotify_track)
            if tidal_track:
                download(
                    f"https://tidal.com/track/{tidal_track.id}",
                    display_name=spotify_track["name"],
                    refresh_callback=self._refresh_td_token,
                    reauth_callback=self._reauth_td_session,
                )
            else:
                print(t.log(f"could not find '{spotify_track['name']}' on TIDAL"))

    def _download_tidal_playlist(
        self, playlist, tracks=None, playlist_number=1, playlist_total=1,
        progress=None, total_tracks=None, skipped_tracks=None, overall=None,
    ):
        if tracks is None:
            tracks = asyncio.run(get_all_playlist_tracks(playlist))
        total = len(tracks)
        display_total = (
            total_tracks
            if total_tracks is not None
            else total + len(skipped_tracks or [])
        )
        skipped_tracks = skipped_tracks or []
        own_progress = progress is None
        if own_progress:
            progress = DownloadProgress(
                total=total,
                desc=t.busy("downloading:"),
                unit="track",
                ncols=120,
                bar_format=DOWNLOAD_BAR_FORMAT,
                file=sys.stdout,
            )
            progress.downloaded_count = 0
            progress.download_total = total
        settings = Files.SETTINGS.load() or {}
        try:
            download_timeout = max(
                30,
                int(settings.get("tidekeeper", {}).get(
                    "downloadTimeoutSeconds", 300
                )),
            )
        except (TypeError, ValueError):
            download_timeout = 300
        playlist_label = t.grey(f"'{playlist.name}'")
        progress.set_description(t.busy("downloading:"), refresh=False)
        header = ""
        if overall and playlist_total > 1:
            downloaded_so_far = getattr(progress, "downloaded_count", 0)
            already_available = overall["skipped_total"] + downloaded_so_far
            still_to_download = overall["pending_total"] - downloaded_so_far
            header += t.busy("downloaded playlists: ") + (
                f"{playlist_number - 1}/{playlist_total} playlists - "
                f"{overall['total_tracks']} tracks "
            ) + t.grey(
                f"({already_available} already available, "
                f"{still_to_download} to download)"
            ) + "\n"
        header += t.busy(
            f"{playlist_label} ({display_total} tracks, {total} to download) - "
            f"playlist {playlist_number}/{playlist_total}"
        )
        tqdm.write("\n\n\n\n" + header, file=sys.stdout)
        batches = [
            tracks[start:start + self.batch_size]
            for start in range(0, total, self.batch_size)
        ]

        def download_batch(batch_number, batch):
            batch_context = t.grey(
                f"/{len(batches)} ({len(batch)} track{'s' if len(batch) != 1 else ''}): "
                f"playlist {playlist_number}/{playlist_total} - '{playlist.name}'"
            )
            progress.clear()
            tqdm.write(
                "\n" + t.busy(f"downloading batch {batch_number}") + batch_context,
                file=sys.stdout,
            )
            for track in batch:
                tqdm.write(t.grey(f"  {track.name}"), file=sys.stdout)
            tqdm.write("", file=sys.stdout)
            downloaded = 0
            processed = 0
            errors = 0
            for track in batch:
                track_progress = 0.0

                def update_track_progress(percent):
                    nonlocal track_progress
                    target = max(track_progress, min(1.0, percent / 100))
                    progress.update(target - track_progress)
                    track_progress = target

                try:
                    progress.clear()
                    tqdm.write(
                        t.busy(f"downloading {track.name}"), file=sys.stdout
                    )
                    result = download(
                        f"https://tidal.com/track/{track.id}",
                        timeout=download_timeout,
                        display_name=track.name,
                        cleanup_partials=False,
                        return_titles=True,
                        refresh_callback=self._refresh_td_token,
                        reauth_callback=self._reauth_td_session,
                        progress_callback=update_track_progress,
                    )
                    if result is None:
                        errors += 1
                    elif result[1] or result[2]:
                        processed += 1
                        if result[1]:
                            downloaded += 1
                        progress.update(1 - track_progress)
                        track_progress = 1.0
                        progress.clear()
                        if result[1]:
                            title = result[1][0] if result[1] else track.name
                            progress.downloaded_count += 1
                            percentage = (
                                0 if progress.download_total == 0
                                else progress.downloaded_count / progress.download_total * 100
                            )
                            tqdm.write(t.log(
                                f"downloaded {t.grey(title)} "
                                f"({progress.downloaded_count}/{progress.download_total} - "
                                f"{percentage:.0f}%)"
                            ) + "\n", file=sys.stdout)
                        else:
                            linked_existing = len(result) > 3 and result[3]
                            suffix = " " + t.grey("(linked database ids)") if linked_existing else ""
                            tqdm.write(
                                t.busy(" skipped ") + t.grey(track.name) + suffix + "\n",
                                file=sys.stdout,
                            )
                except Exception as error:
                    if isinstance(error, TidalSessionStaleError):
                        raise
                    if track_progress:
                        progress.update(-track_progress)
                    errors += 1
                    tqdm.write(
                        t.error(f"failed to download '{track.name}': {error}") + "\n",
                        file=sys.stdout,
                    )
            return downloaded, errors, processed

        try:
            for batch_number, batch in enumerate(batches, 1):
                download_batch(batch_number, batch)
            clean_tmp(Files.SETTINGS.load().get("flacDirectory"))
        finally:
            if own_progress:
                progress.close()

    def _find_tidal_track(self, spotify_track):
        query = f"{spotify_track['name']} {spotify_track['artists'][0]['name']}"
        results = self.td_session.search(query, models=[tidalapi.media.Track])
        for tidal_track in results.get("tracks", []):
            if match(tidal_track, spotify_track):
                return tidal_track
        return None

    def _sync_playlist(self, spotify_id):
        spotify_playlist = self.sp_session.playlist(spotify_id)
        tidal_playlists = get_td_playlists_wrapper(self.td_session)
        tidal_playlist = pick_td_playlist_for_sp_playlist(
            spotify_playlist, tidal_playlists
        )[1]
        sync_playlists_wrapper(
            self.sp_session,
            self.td_session,
            [(spotify_playlist, tidal_playlist)],
            self.sp_credentials,
        )
        return tidal_playlist
