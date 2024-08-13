import asyncio
import math
import tidalapi
import td_sync as _td_sync
from td_fetcher_helper import add_multiple_tracks_to_playlist, clear_tidal_playlist, get_all_favorites, get_all_playlists, get_all_playlist_tracks, get_all_playlist_tracks
from typing import List, Mapping
from tidalapi.request import Requests
from tidalapi.session import Session
from tqdm.asyncio import tqdm as atqdm

class TidalFetcher(Requests):
    def __init__(self, session: "Session"):
        super().__init__(session)


    def get_playlist_by_id(session, playlist_id):
        requests_instance = Requests(session)
        path = f"playlists/{playlist_id}"

        try:
            response = requests_instance.request("GET", path)
            playlist_data = response
        except Exception as e:
            print(f"An error occurred: {e}")
        return playlist_data




    async def get_tidal_playlists_wrapper(tidal_session: tidalapi.Session) -> Mapping[str, tidalapi.Playlist]:
        tidal_playlists = await get_all_playlists(tidal_session.user)
        return {playlist.name: playlist for playlist in tidal_playlists}


    async def pick_tidal_playlist_for_spotify_playlist(spotify_playlist_name: str, tidal_playlists: Mapping[str, tidalapi.Playlist]):
        if spotify_playlist_name in tidal_playlists:
            tidal_playlist = tidal_playlists[spotify_playlist_name]
            return tidal_playlist
        else:
            return None


    async def get_playlists_names_ids(tidal_session: tidalapi.Session) -> Mapping[str, tidalapi.Playlist]:
        playlists_data = await get_all_playlists(tidal_session.user)
        # print("> Fetching tidal playlists")
        # print(f" > Total tidal playlists: {playlists_data['total']}")
        playlists = [{"id": p.id, "name": p.name, 'sync': 'off'}
                    for p in playlists_data]

        # for p in playlists:
        #    print(f"    {p['id']}  {p['name']}")

        return playlists


    async def find_matching_playlist(sp_playlist, td_playlists):
        for tdp in td_playlists:
            if sp_playlist['name'] == tdp['name']:
                return tdp['id']
        print(f"> Didn't find a matching playlist for {sp_playlist['name']}")
        td_playlist = _td_sync.create_new_playlist(sp_playlist)
        return td_playlist.id

    async def get_all_playlists(self, chunk_size: int = 10):
        params = {
            "limit": chunk_size,
        }

        chunks = await self._get_all_chunks(
            f"users/{self.user.id}/playlists",
            session=self,
            parser=self.user.playlist.parse_factory,
            params=params,
        )

        return chunks

    async def get_all_playlist_tracks(self, playlist, chunk_size: int = 20):
        params = {
            "limit": chunk_size,
        }
        return await self._get_all_chunks(
            f"{playlist._base_url%playlist.id}/tracks",
            session=self,
            parser=playlist.session.parse_track,
            params=params,
        )

    async def get_tidal_playlists_wrapper(self):
        tidal_playlists = await self.get_all_playlists()
        return {playlist.name: playlist for playlist in tidal_playlists}

    async def pick_tidal_playlist_for_spotify_playlist(
        self, spotify_playlist_name, tidal_playlists
    ):
        if spotify_playlist_name in tidal_playlists:
            tidal_playlist = tidal_playlists[spotify_playlist_name]
            return tidal_playlist
        else:
            return None

    async def get_playlists_names_ids(self):
        playlists_data = await self.get_all_playlists()
        playlists = [{"id": p.id, "name": p.name, "sync": "off"} for p in playlists_data]

        return playlists

    async def find_matching_playlist(self, sp_playlist, td_playlists):
        for tdp in td_playlists:
            if sp_playlist["name"] == tdp["name"]:
                return tdp






###



