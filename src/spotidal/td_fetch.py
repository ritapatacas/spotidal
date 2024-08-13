import asyncio
import math
import tidalapi
import td_sync as _td_sync
from td_fetcher_helper import _get_all_chunks
from typing import List, Mapping
from tidalapi.request import Requests
from tidalapi.session import Session
from tqdm.asyncio import tqdm as atqdm


class TidalFetcher:
    def __init__(self, session: "Session"):
        self.td = session

    #this is just a try to do it without tidalapi
    def get_playlist_by_id(self, playlist_id):
        requests_instance = Requests(self.td)
        path = f"playlists/{playlist_id}"

        try:
            response = requests_instance.request("GET", path)
            playlist_data = response
        except Exception as e:
            print(f"An error occurred: {e}")
        return playlist_data


    async def get_playlists_names_ids(self) -> Mapping[str, tidalapi.Playlist]:
        playlists_data = await get_all_playlists(self.td.user)
        # print("> Fetching tidal playlists")
        # print(f" > Total tidal playlists: {playlists_data['total']}")
        playlists = [{"id": p.id, "name": p.name, 'sync': 'off'}
                    for p in playlists_data]

        # for p in playlists:
        #    print(f"    {p['id']}  {p['name']}")

        return playlists

    async def get_all_playlists(self, chunk_size: int=10) -> List[tidalapi.Playlist]:
        """ Get all user playlists from Tidal in chunks """
        print(f"Loading playlists from Tidal user")
        params = {
            "limit": chunk_size,
        }
        return await _get_all_chunks(f"users/{self.td.user.id}/playlists", self.td, parser=self.td.user.playlist.parse_factory, params=params)

    def get_tidal_playlists_wrapper(self) -> Mapping[str, tidalapi.Playlist]:
        tidal_playlists = asyncio.run(self.get_all_playlists(self))
        return {playlist.name: playlist for playlist in tidal_playlists}

    async def get_all_playlist_tracks(playlist: tidalapi.Playlist, chunk_size: int=20) -> List[tidalapi.Track]:
        """ Get all tracks from Tidal playlist in chunks """
        params = {
            "limit": chunk_size,
        }
        print(f"Loading tracks from Tidal playlist '{playlist.name}'")
        return await _get_all_chunks(f"{playlist._base_url%playlist.id}/tracks", session=playlist.session, parser=playlist.session.parse_track, params=params)

