import asyncio
import math
import tidalapi
from typing import List, Mapping
from tqdm.asyncio import tqdm as atqdm

# based on git@github.com:spotify2tidal/spotify_to_tidal.git


async def _get_all_chunks(url, session, parser, params={}) -> List[tidalapi.Track]:
    """
        Helper function to get all items from a Tidal endpoint in parallel
        The main library doesn't provide the total number of items or expose the raw json, so use this wrapper instead
    """
    def _make_request(offset: int = 0):
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
            *[asyncio.to_thread(lambda offset: session.request.map_json(
                _make_request(offset), parse=parser), offset) for offset in offsets],
            desc="> Fetching additional data chunks"
        )
        for extra_result in extra_results:
            items.extend(extra_result)
    print(f" > Total tidal playlists: {len(items)}")
    return items


async def get_all_playlists(user: tidalapi.User, chunk_size: int = 10) -> List[tidalapi.Playlist]:
    """ Get all user playlists from Tidal in chunks """
    print(f"\n\n> Fetching tidal playlists")
    params = {
        "limit": chunk_size,
    }

    chunks = await _get_all_chunks(f"users/{user.id}/playlists", session=user.session, parser=user.playlist.parse_factory, params=params)

    #for playlist in chunks:
    #    print("   ", playlist.id, playlist.name)

    return chunks


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
    #print("> Fetching tidal playlists")
    #print(f" > Total tidal playlists: {playlists_data['total']}")
    playlists = [{"id": p.id, "name": p.name, 'sync': 'off' } for p in playlists_data]

    #for p in playlists:
    #    print(f"    {p['id']}  {p['name']}")

    return playlists
