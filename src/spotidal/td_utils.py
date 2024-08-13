import asyncio
import math
import tidalapi
import td_sync as _td_sync
from typing import List, Mapping
from spotidal.td_utils import Requests
from tqdm.asyncio import tqdm as atqdm


# based on git@github.com:spotify2tidal/spotify_to_tidal.git

async def pick_tidal_playlist_for_spotify_playlist(spotify_playlist_name: str, tidal_playlists: Mapping[str, tidalapi.Playlist]):
    if spotify_playlist_name in tidal_playlists:
        tidal_playlist = tidal_playlists[spotify_playlist_name]
        return tidal_playlist
    else:
        return None


async def find_matching_playlist(sp_playlist, td_playlists):
    for tdp in td_playlists:
        if sp_playlist['name'] == tdp['name']:
            return tdp['id']
    print(f"> Didn't find a matching playlist for {sp_playlist['name']}")
    td_playlist = _td_sync.create_new_playlist(sp_playlist)
    return td_playlist.id

