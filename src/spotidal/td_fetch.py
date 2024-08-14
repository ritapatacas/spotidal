import asyncio
import math
import tidalapi

from typing import List, Mapping
from tqdm import tqdm
from tqdm.asyncio import tqdm as atqdm

""" async def pick_tidal_playlist_for_spotify_playlist(spotify_playlist_name: str, tidal_playlists: Mapping[str, tidalapi.Playlist]):
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

"""



#### from tidapapi_patch on git@github.com:spotify2tidal/spotify_to_tidal.git

def _remove_indices_from_playlist(playlist: tidalapi.UserPlaylist, indices: List[int]):
    headers = {'If-None-Match': playlist._etag}
    index_string = ",".join(map(str, indices))
    playlist.request.request('DELETE', (playlist._base_url + '/items/%s') % (playlist.id, index_string), headers=headers)
    playlist._reparse()

def clear_tidal_playlist(playlist: tidalapi.UserPlaylist, chunk_size: int=20):
    with tqdm(desc="Erasing existing tracks from Tidal playlist", total=playlist.num_tracks) as progress:
        while playlist.num_tracks:
            indices = range(min(playlist.num_tracks, chunk_size))
            _remove_indices_from_playlist(playlist, indices)
            progress.update(len(indices))

def add_multiple_tracks_to_playlist(playlist: tidalapi.UserPlaylist, track_ids: List[int], chunk_size: int=20):
    offset = 0
    with tqdm(desc="Adding new tracks to Tidal playlist", total=len(track_ids)) as progress:
        while offset < len(track_ids):
            count = min(chunk_size, len(track_ids) - offset)
            playlist.add(track_ids[offset:offset+chunk_size])
            offset += count
            progress.update(count)

async def _get_all_chunks(url, session: tidalapi.Session, parser, params={}) -> List[tidalapi.Track]:
    """
        Helper function to get all items from a Tidal endpoint in parallel
        The main library doesn't provide the total number of items or expose the raw json, so use this wrapper instead
    """
    def _make_request(offset: int=0):
        new_params = params
        new_params['offset'] = offset
        return session.request.map_request(url, params=new_params)

    first_chunk_raw = _make_request()
    limit = first_chunk_raw['limit']
    total = first_chunk_raw['totalNumberOfItems']
    items = session.request.map_json(first_chunk_raw, parse=parser)

    if len(items) < total:
        offsets = [limit * n for n in range(1, math.ceil(total/limit))]
        extra_results = await atqdm.gather(
                *[asyncio.to_thread(lambda offset: session.request.map_json(_make_request(offset), parse=parser), offset) for offset in offsets],
            desc="Fetching additional data chunks"
        )
        for extra_result in extra_results:
            items.extend(extra_result)
    return items

async def get_all_favorites(favorites: tidalapi.Favorites, order: str = "NAME", order_direction: str = "ASC", chunk_size: int=100) -> List[tidalapi.Track]:
    """ Get all favorites from Tidal playlist in chunks """
    params = {
        "limit": chunk_size,
        "order": order,
        "orderDirection": order_direction,
    }
    return await _get_all_chunks(f"{favorites.base_url}/tracks", session=favorites.session, parser=favorites.session.parse_track, params=params)

async def get_all_playlists(user: tidalapi.User, chunk_size: int=10) -> List[tidalapi.Playlist]:
    """ Get all user playlists from Tidal in chunks """
    print(f"Loading playlists from Tidal user")
    params = {
        "limit": chunk_size,
    }
    return await _get_all_chunks(f"users/{user.session.user.id}/playlists", session=user.session, parser=user.playlist.parse_factory, params=params)

async def get_all_playlist_tracks(playlist: tidalapi.Playlist, chunk_size: int=20) -> List[tidalapi.Track]:
    """ Get all tracks from Tidal playlist in chunks """
    params = {
        "limit": chunk_size,
    }
    print(f"Loading tracks from Tidal playlist '{playlist.name}'")
    return await _get_all_chunks(f"{playlist._base_url%playlist.id}/tracks", session=playlist.session, parser=playlist.session.parse_track, params=params)

###
