import asyncio
import json
import math
from typing import List
import tidalapi
from tqdm import tqdm
from tqdm.asyncio import tqdm as atqdm


async def _get_all_chunks(url, session, parser, params={}) -> List[tidalapi.Track]:
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

async def get_all_playlists(user: tidalapi.User, chunk_size: int=10) -> List[tidalapi.Playlist]:
    """ Get all user playlists from Tidal in chunks """
    print(f"\n\nLoading playlists from Tidal user\n")
    params = {
        "limit": chunk_size,
    }

    chunks = await _get_all_chunks(f"users/{user.id}/playlists", session=user.session, parser=user.playlist.parse_factory, params=params)

    for playlist in chunks:
        print(playlist.id, playlist.name)

    return chunks
