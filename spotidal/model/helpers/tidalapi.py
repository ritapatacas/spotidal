import asyncio
import math
import time
import tidalapi
from typing import List
from tqdm import tqdm
from tqdm.asyncio import tqdm as atqdm
from spotidal.view.text import Text as t


progress_color = "\033[38;5;102m"
reset_color = "\033[0m"


def _remove_indices_from_playlist(
    playlist: tidalapi.UserPlaylist, indices: List[int], attempts: int = 5
):
    index_string = ",".join(map(str, indices))
    for attempt in range(attempts):
        try:
            playlist.request.request(
                "DELETE",
                (playlist._base_url + "/items/%s") % (playlist.id, index_string),
                headers={"If-None-Match": playlist._etag},
            )
            playlist._reparse()
            return
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            # 412: stale etag. 400: indices out of range (server state drifted
            # from our local count). Resync and retry with backoff.
            if status not in (400, 412):
                raise
            time.sleep(0.5 * (attempt + 1))
            playlist._reparse()

def clear_td_playlist(playlist: tidalapi.UserPlaylist, chunk_size: int = 20):
    playlist._reparse()
    with tqdm(
        desc="> erasing existing tracks from tidal playlist", total=playlist.num_tracks
    ) as progress:
        stalled = 0
        while playlist.num_tracks:
            before = playlist.num_tracks
            indices = range(min(before, chunk_size))
            _remove_indices_from_playlist(playlist, indices)
            removed = before - playlist.num_tracks
            progress.update(max(0, removed))
            stalled = stalled + 1 if removed <= 0 else 0
            if stalled:
                # num_tracks metadata can lag behind reality; trust the actual
                # track listing before retrying or declaring failure
                if not playlist.tracks(limit=1):
                    progress.update(playlist.num_tracks)
                    break
                time.sleep(1.0 * stalled)
                playlist._reparse()
            if stalled >= 5:
                raise RuntimeError(
                    "could not erase tracks from tidal playlist '%s' (no progress after 5 attempts)"
                    % playlist.name
                )

def add_multiple_tracks_to_playlist(
    playlist: tidalapi.UserPlaylist, track_ids: List[int], chunk_size: int = 20
):
    offset = 0
    with tqdm(
        desc=t.busy('adding new tracks to tidal playlist'), total=len(track_ids)
    ) as progress:
        while offset < len(track_ids):
            count = min(chunk_size, len(track_ids) - offset)
            if not playlist._etag:
                playlist._reparse()
            try:
                playlist.add(track_ids[offset : offset + chunk_size])
            except Exception as error:
                if getattr(getattr(error, "response", None), "status_code", None) != 412:
                    raise
                playlist._reparse()
                playlist.add(track_ids[offset : offset + chunk_size])
            offset += count
            progress.update(count)

async def _get_all_chunks(url, session, parser, params={}) -> List[tidalapi.Track]:
    """
    Helper function to get all items from a Tidal endpoint in parallel
    The main library doesn't provide the total number of items or expose the raw json, so use this wrapper instead
    """

    def _make_request(offset: int = 0):
        new_params = params
        new_params["offset"] = offset
        return session.request.map_request(url, params=new_params)

    first_chunk_raw = _make_request()
    limit = first_chunk_raw["limit"]
    total = first_chunk_raw["totalNumberOfItems"]
    items = session.request.map_json(first_chunk_raw, parse=parser)

    if len(items) < total:
        offsets = [limit * n for n in range(1, math.ceil(total / limit))]
        extra_results = await atqdm.gather(
            *[
                asyncio.to_thread(
                    lambda offset: session.request.map_json(
                        _make_request(offset), parse=parser
                    ),
                    offset,
                )
                for offset in offsets
            ],
            desc=t.busy("fetching additional data chunks"),
            bar_format=f"{progress_color}{{l_bar}}{{bar}}| {{n_fmt}}/{{total_fmt}} ",
        )
        for extra_result in extra_results:
            items.extend(extra_result)
    return items

async def get_all_favorites(
    favorites: tidalapi.Favorites,
    order: str = "NAME",
    order_direction: str = "ASC",
    chunk_size: int = 100,
) -> List[tidalapi.Track]:
    """Get all favorites from Tidal playlist in chunks"""
    params = {
        "limit": chunk_size,
        "order": order,
        "orderDirection": order_direction,
    }
    return await _get_all_chunks(
        f"{favorites.base_url}/tracks",
        session=favorites.session,
        parser=favorites.session.parse_track,
        params=params,
    )

async def get_all_playlists(
    user: tidalapi.User, chunk_size: int = 10
) -> List[tidalapi.Playlist]:
    """Get all user playlists from Tidal in chunks"""
    print(t.busy(f"loading playlists from Tidal user"))
    params = {
        "limit": chunk_size,
    }
    return await _get_all_chunks(
        f"users/{user.id}/playlists",
        session=user.session,
        parser=user.playlist.parse_factory,
        params=params,
    )

async def get_all_playlist_tracks(
    playlist: tidalapi.Playlist, chunk_size: int = 20
) -> List[tidalapi.Track]:
    """Get all tracks from tidal playlist in chunks"""
    params = {
        "limit": chunk_size,
    }
    print(t.busy(f"loading tracks from tidal playlist '{playlist.name}'"))
    return await _get_all_chunks(
        f"{playlist._base_url%playlist.id}/tracks",
        session=playlist.session,
        parser=playlist.session.parse_track,
        params=params,
    )
