import asyncio
from typing import Callable, List, Mapping
import math
import spotipy
import tidalapi
from tqdm.asyncio import tqdm as atqdm
import math
from spotidal.src.model.helpers.tidalapi import get_all_playlists
from spotidal.src.view.text import Text as t
import spotidal.src.model.helpers.sync.search as _search
import spotidal.src.model.helpers.sync.request_utils as _req


def get_td_playlists_wrapper(
    td_session: tidalapi.Session,
) -> Mapping[str, tidalapi.Playlist]:
    tidal_playlists = asyncio.run(get_all_playlists(td_session.user))
    return {playlist.name: playlist for playlist in tidal_playlists}

def get_td_playlists(
    td_session: tidalapi.Session,
) -> Mapping[str, tidalapi.Playlist]:
    return get_td_playlists_wrapper(td_session).values()

def get_user_playlist_mappings(
    sp_session: spotipy.Spotify, td_session: tidalapi.Session, config
):
    results = []
    spotify_playlists = asyncio.run(get_playlists_from_sp(sp_session, config))
    tidal_playlists = get_td_playlists_wrapper(td_session)
    for spotify_playlist in spotify_playlists:
        results.append(
            _search.pick_td_playlist_for_sp_playlist(
                spotify_playlist, tidal_playlists
            )
        )
    return results

async def _fetch_all_from_sp_in_chunks(fetch_function: Callable) -> List[dict]:
    output = []
    results = fetch_function(0)
    output.extend(
        [item["track"] for item in results["items"] if item["track"] is not None]
    )

    # Get all the remaining tracks in parallel
    if results["next"]:
        offsets = [
            results["limit"] * n
            for n in range(1, math.ceil(results["total"] / results["limit"]))
        ]
        extra_results = await atqdm.gather(
            *[asyncio.to_thread(fetch_function, offset) for offset in offsets],
            desc="fetching additional data chunks",
        )
        for r in extra_results:
            output.extend(
                [
                    item["track"]
                    for item in r["items"]
                    if item["track"] is not None
                ]
            )

    return output

async def get_playlists_from_sp(sp_session: spotipy.Spotify, config):
    # get all the playlists from the Spotify account
    playlists = []
    print(t.busy(f"loading Spotify playlists"))
    first_results = sp_session.current_user_playlists()
    exclude_list = set([x.split(":")[-1] for x in config.get("excluded_playlists", [])])
    playlists.extend([p for p in first_results["items"]])
    user_id = sp_session.current_user()["id"]

    # get all the remaining playlists in parallel
    if first_results["next"]:
        offsets = [
            first_results["limit"] * n
            for n in range(
                1, math.ceil(first_results["total"] / first_results["limit"])
            )
        ]
        extra_results = await atqdm.gather(
            *[
                asyncio.to_thread(sp_session.current_user_playlists, offset=offset)
                for offset in offsets
            ]
        )
        for r in extra_results:
            playlists.extend([p for p in r["items"]])

    # filter out playlists that don't belong to us or are on the exclude list
    def my_playlist_filter(p):
        return p["owner"]["id"] == user_id

    def exclude_filter(p):
        return not p["id"] in exclude_list

    return list(filter(exclude_filter, filter(my_playlist_filter, playlists)))

async def get_tracks_from_sp_playlist(
    sp_session: spotipy.Spotify, sp_playlist
):
    def _get_tracks_from_sp_playlist(offset: int, playlist_id: str):
        fields = "next,total,limit,items(track(name,album(name,artists),artists,track_number,duration_ms,id,external_ids(isrc))),type"
        return sp_session.playlist_tracks(
            playlist_id=playlist_id, fields=fields, offset=offset
        )

    print(t.busy(f"loading tracks from spotify playlist '{sp_playlist['name']}'"))
    items = await _req.repeat_on_request_error(
        _fetch_all_from_sp_in_chunks,
        lambda offset: _get_tracks_from_sp_playlist(
            offset=offset, playlist_id=sp_playlist["id"]
        ),
    )

    def track_filter(item):
        return item.get("type", "track") == "track"  # type may be 'episode' also

    return list(filter(track_filter, items))
