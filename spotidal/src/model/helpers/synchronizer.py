import asyncio
from typing import List
import spotipy
import tidalapi
from tqdm import tqdm
from spotidal.src.model.helpers.cache import track_match_cache
from spotidal.src.model.helpers.tidalapi import (
    add_multiple_tracks_to_playlist,
    clear_td_playlist,
    get_all_favorites,
    get_all_playlist_tracks,
)
from spotidal.src.view.text import Text as t
import spotidal.src.model.helpers.sync.match as _match
import spotidal.src.model.helpers.sync.search as _search
import spotidal.src.model.helpers.sync.cache as _cache
import spotidal.src.model.helpers.sync.request_utils as _req
import spotidal.src.model.helpers.sync.playlists_handler as _playlists


async def sync_playlist(
    sp_session: spotipy.Spotify,
    td_session: tidalapi.Session,
    sp_playlist,
    td_playlist: tidalapi.Playlist | None,
    config: dict,
):
    sp_tracks = await _playlists.get_tracks_from_sp_playlist(
        sp_session, sp_playlist
    )
    if len(sp_tracks) == 0:
        return
    if td_playlist:
        old_td_tracks = await get_all_playlist_tracks(td_playlist)
    else:
        print(
            f"> no playlist found on tidal corresponding to spotify playlist: '{sp_playlist['name']}', creating new playlist"
        )
        td_playlist = td_session.user.create_playlist(
            sp_playlist["name"], sp_playlist["description"]
        )
        old_td_tracks = []

    # extract the new tracks we haven't already seen
    _cache.populate_track_match_cache(sp_tracks, old_td_tracks)
    await _search.search_new_tracks_on_td(
        td_session, sp_tracks, sp_playlist["name"], config
    )
    new_td_track_ids = _cache.get_tracks_for_new_td_playlist(sp_tracks)

    # update the tidal playlist if there are changes
    old_td_track_ids = [t.id for t in old_td_tracks]
    if new_td_track_ids == old_td_track_ids:
        print(t.log("no changes to write to tidal playlist"))
    elif new_td_track_ids[: len(old_td_track_ids)] == old_td_track_ids:
        add_multiple_tracks_to_playlist(
            td_playlist, new_td_track_ids[len(old_td_track_ids) :]
        )
    else:
        # todo check tracks that are not in spotify
        # erase old playlist and add new tracks from scratch if any reordering occurred
        clear_td_playlist(td_playlist)
        add_multiple_tracks_to_playlist(td_playlist, new_td_track_ids)

async def sync_favorites(
    sp_session: spotipy.Spotify, td_session: tidalapi.Session, config: dict
):
    async def get_tracks_from_spotify_favorites() -> List[dict]:
        _get_fav_tracks = lambda offset: sp_session.current_user_saved_tracks(
            offset=offset
        )
        tracks = await _req.repeat_on_request_error(
            _playlists._fetch_all_from_sp_in_chunks, _get_fav_tracks
        )
        tracks.reverse()
        return tracks

    def get_new_td_favorites() -> List[int]:
        existing_fav_ids = set([track.id for track in old_td_tracks])
        new_ids = []
        for t in sp_tracks:
            match_id = track_match_cache.get(t["id"])
            if match_id and not match_id in existing_fav_ids:
                new_ids.append(match_id)
        return new_ids

    print(t.busy("loading favorite tracks from spotify"))
    sp_tracks = await get_tracks_from_spotify_favorites()
    print(t.busy("loading existing favorite tracks from tidal"))
    old_td_tracks = await get_all_favorites(
        td_session.user.favorites, order="DATE"
    )
    _match.populate_track_match_cache(sp_tracks, old_td_tracks)
    await _search.search_new_tracks_on_td(
        td_session, sp_tracks, "Favorites", config
    )
    new_tidal_favorite_ids = get_new_td_favorites()
    if new_tidal_favorite_ids:
        for tidal_id in tqdm(
            new_tidal_favorite_ids, desc="> adding new tracks to tidal favorites"
        ):
            td_session.user.favorites.add_track(tidal_id)
    else:
        print(t.error("> no new tracks to add to tidal favorites"))

def sync_playlists_wrapper(
    sp_session: spotipy.Spotify,
    td_session: tidalapi.Session,
    playlists,
    config: dict,
):
    for sp_playlist, td_playlist in playlists:
        # sync the spotify playlist to tidal
        asyncio.run(
            sync_playlist(
                sp_session, td_session, sp_playlist, td_playlist, config
            )
        )

def sync_favorites_wrapper(
    sp_session: spotipy.Spotify, td_session: tidalapi.Session, config
):
    asyncio.run(
        main=sync_favorites(
            sp_session=sp_session, td_session=td_session, config=config
        )
    )
