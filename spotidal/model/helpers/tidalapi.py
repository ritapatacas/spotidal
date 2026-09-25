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


def _remove_indices_from_playlist(playlist: tidalapi.UserPlaylist, indices: List[int]):
    headers = {"If-None-Match": playlist._etag}
    index_string = ",".join(map(str, indices))
    playlist.request.request(
        "DELETE",
        (playlist._base_url + "/items/%s") % (playlist.id, index_string),
        headers=headers,
    )
    playlist._reparse()

def clear_td_playlist(playlist: tidalapi.UserPlaylist, chunk_size: int = 20, max_retries: int = 10):
    if not playlist._etag:
        playlist._reparse()
    with tqdm(
        desc="> erasing existing tracks from tidal playlist", total=playlist.num_tracks
    ) as progress:
        while playlist.num_tracks:
            before = playlist.num_tracks
            # A stale etag (412) can mean a previous delete partially landed
            # server-side, or that something else touched the playlist
            # concurrently — either way, re-fetch the current track count and
            # try again rather than giving up after one retry. A single
            # unhandled 412 here used to propagate all the way up and crash
            # the whole app mid-erase, potentially leaving the real TIDAL
            # playlist with only some tracks removed and nothing re-added.
            for attempt in range(max_retries):
                indices = range(min(playlist.num_tracks, chunk_size))
                try:
                    _remove_indices_from_playlist(playlist, indices)
                    break
                except Exception as error:
                    if getattr(getattr(error, "response", None), "status_code", None) != 412:
                        raise
                    playlist._reparse()
                    if not playlist.num_tracks:
                        break
                    if attempt == max_retries - 1:
                        raise RuntimeError(
                            f"giving up clearing tidal playlist '{playlist.name}' "
                            f"after {max_retries} consecutive 412s (etag kept going "
                            "stale) — playlist may be left partially cleared"
                        ) from error
            progress.update(before - playlist.num_tracks)

def swap_track_in_playlist(playlist: tidalapi.UserPlaylist, old_track_id: int, new_track_id: int):
    """Replace one track with another in-place. Used when an "original
    album" review decision arrives after the playlist was already built
    with the Spotify-side track — position isn't preserved (the
    replacement lands at the end), which is an acceptable tradeoff for
    something that should be rare."""
    tracks = playlist.tracks()
    indices = [i for i, track in enumerate(tracks) if track.id == old_track_id]
    if indices:
        _remove_indices_from_playlist(playlist, indices)
    add_multiple_tracks_to_playlist(playlist, [new_track_id])


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

async def _get_all_chunks(url, session, parser, params={}, show_progress=True) -> List[tidalapi.Track]:
    """
    Helper function to get all items from a Tidal endpoint in parallel
    The main library doesn't provide the total number of items or expose the raw json, so use this wrapper instead
    """

    def _make_request(offset: int = 0):
        new_params = {**params, "offset": offset}
        last_error = None
        for attempt in range(3):
            try:
                return session.request.map_request(url, params=new_params)
            except Exception as error:
                last_error = error
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise last_error

    first_chunk_raw = _make_request()
    limit = first_chunk_raw["limit"]
    total = first_chunk_raw["totalNumberOfItems"]
    items = session.request.map_json(first_chunk_raw, parse=parser)

    if len(items) < total:
        offsets = [limit * n for n in range(1, math.ceil(total / limit))]
        chunk_requests = [
            asyncio.to_thread(
                lambda offset: session.request.map_json(
                    _make_request(offset), parse=parser
                ),
                offset,
            )
            for offset in offsets
        ]
        if show_progress:
            extra_results = await atqdm.gather(
                *chunk_requests,
                desc=t.busy("fetching additional data chunks"),
                ncols=70,
                leave=False,
                bar_format=(
                    f"{progress_color}{{desc}}: {{percentage:3.0f}}%|"
                    "{bar:20}| {n_fmt}/{total_fmt}"
                ),
            )
        else:
            extra_results = await asyncio.gather(*chunk_requests)
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
    tqdm.write(t.busy(f"loading playlists from Tidal user"))
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
    playlist: tidalapi.Playlist, chunk_size: int = 20, show_log: bool = True,
    show_progress: bool = True,
) -> List[tidalapi.Track]:
    """Get all tracks from tidal playlist in chunks"""
    params = {
        "limit": chunk_size,
    }
    if show_log:
        print("\n" + t.busy(f"loading tracks from tidal playlist '{playlist.name}'"))
    return await _get_all_chunks(
        f"{playlist._base_url%playlist.id}/tracks",
        session=playlist.session,
        parser=playlist.session.parse_track,
        params=params,
        show_progress=show_progress,
    )
