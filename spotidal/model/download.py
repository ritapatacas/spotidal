from urllib.parse import urlparse

import tidalapi

from .helpers import download
from .helpers.utils import list_handler
from .helpers.type.file import Files
from .helpers.sync.match import match
from .helpers.sync.playlists_handler import get_td_playlists_wrapper
from .helpers.sync.search import pick_td_playlist_for_sp_playlist
from .helpers.synchronizer import sync_playlists_wrapper
from .library import MusicLibrary

class Download:
    def __init__(self, sessions):
        self.sp_session = sessions["sp"]
        self.td_session = sessions["td"]
        self.sp_credentials = Files.CREDENTIALS.load()["spotify"]

    def _download_by_td_id(self, td_id):
        download(td_id)

    def by_td_id(self, td_id):
        list_handler(td_id, self._download_by_td_id)

    def by_url(self, url):
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
            completed = download(url.strip())
            if playlist and completed:
                MusicLibrary(Files.SETTINGS.load().get("downloadPath", "~/Spotidal2U")).associate_tidal_playlist(playlist, media_id)
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
            completed = download(f"https://tidal.com/playlist/{td_playlist.id}")
            if completed:
                MusicLibrary(Files.SETTINGS.load().get("downloadPath", "~/Spotidal2U")).associate_tidal_playlist(td_playlist, str(td_playlist.id))
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
                download(f"https://tidal.com/track/{tidal_track.id}")
            else:
                print(f"> could not find '{spotify_track['name']}' on TIDAL")

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
