import asyncio
import datetime
from typing import Sequence, Mapping
import tidalapi
from tqdm.asyncio import tqdm as atqdm
from spotidal.src.model.helpers.cache import failure_cache, track_match_cache
from spotidal.src.model.helpers.type import spotify as t_spotify
from spotidal.src.view.text import Text as t
from spotidal.src.model.helpers.type.file import Files
import spotidal.src.model.helpers.sync.match as _match
import spotidal.src.model.helpers.sync.cache as _cache
import spotidal.src.model.helpers.sync.request_utils as _req
import spotidal.src.model.helpers.sync.search as _search


async def td_search(
    sp_track, rate_limiter, td_session: tidalapi.Session
) -> tidalapi.Track | None:
    def _search_for_track_in_album():
        # search for album name and first album artist
        if (
            "album" in sp_track
            and "artists" in sp_track["album"]
            and len(sp_track["album"]["artists"])
        ):
            query = (
                _match.simple(sp_track["album"]["name"])
                + " "
                + _match.simple(sp_track["album"]["artists"][0]["name"])
            )
            album_result = td_session.search(query, models=[tidalapi.album.Album])
            for album in album_result["albums"]:
                if album.num_tracks >= sp_track[
                    "track_number"
                ] and _match.test_album_similarity(sp_track["album"], album):
                    album_tracks = album.tracks()
                    if len(album_tracks) < sp_track["track_number"]:
                        assert (
                            not len(album_tracks) == album.num_tracks
                        )  # incorrect metadata :(
                        continue
                    track = album_tracks[sp_track["track_number"] - 1]
                    if _match.match(track, sp_track):
                        failure_cache.remove_match_failure(sp_track["id"])
                        return track

    def _search_for_standalone_track():
        # if album search fails then search for track name and first artist
        query = (
            _match.simple(sp_track["name"])
            + " "
            + _match.simple(sp_track["artists"][0]["name"])
        )
        for track in td_session.search(query, models=[tidalapi.media.Track])[
            "tracks"
        ]:
            if _match.match(track, sp_track):
                failure_cache.remove_match_failure(sp_track["id"])
                return track

    await rate_limiter.acquire()
    album_search = await asyncio.to_thread(_search_for_track_in_album)
    if album_search:
        return album_search
    await rate_limiter.acquire()
    track_search = await asyncio.to_thread(_search_for_standalone_track)
    if track_search:
        return track_search

    # if none of the search modes succeeded then store the track id to the failure cache
    failure_cache.cache_match_failure(sp_track["id"])

async def search_new_tracks_on_td(
    td_session: tidalapi.Session,
    sp_tracks: Sequence[t_spotify.SpotifyTrack],
    playlist_name: str,
    config: dict,
):
    """Generic function for searching for each item in a list of Spotify tracks which have not already been seen and adding them to the cache"""

    async def _run_rate_limiter(semaphore):
        """Leaky bucket algorithm for rate limiting. Periodically releases items from semaphore at rate_limit"""
        _sleep_time = (
            config.get("max_concurrency", 10) / config.get("rate_limit", 10) / 4
        )  # aim to sleep approx time to drain 1/4 of 'bucket'
        t0 = datetime.datetime.now()
        while True:
            await asyncio.sleep(_sleep_time)
            t = datetime.datetime.now()
            dt = (t - t0).total_seconds()
            new_items = round(config.get("rate_limit", 10) * dt)
            t0 = t
            # leak new_items from the 'bucket'
            [semaphore.release() for i in range(new_items)]

    # Extract the new tracks that do not already exist in the old tidal tracklist
    tracks_to_search = _cache.get_new_sp_tracks(sp_tracks)
    if not tracks_to_search:
        return

    # Search for each of the tracks on Tidal concurrently
    task_description = (
        "> searching tidal for {}/{} tracks in spotify playlist '{}'".format(
            len(tracks_to_search), len(sp_tracks), playlist_name
        )
    )
    semaphore = asyncio.Semaphore(config.get("max_concurrency", 10))
    rate_limiter_task = asyncio.create_task(_run_rate_limiter(semaphore))
    search_results = await atqdm.gather(
        *[
            _req.repeat_on_request_error(
                _search.td_search, t, semaphore, td_session
            )
            for t in tracks_to_search
        ],
        desc=task_description,
    )
    rate_limiter_task.cancel()

    # todo song404 is for future use with track id to repeat search
    song404 = []
    not_found = []
    for idx, sp_track in enumerate(tracks_to_search):
        if search_results[idx]:
            track_match_cache.insert((sp_track["id"], search_results[idx].id))
        else:
            song404.append(
                [f"{sp_track['id']}", f"{','.join([a['name'] for a in sp_track['artists']])} - {sp_track['name']}"]
            )
            not_found.append(
                f"{sp_track['name']} - {','.join([a['name'] for a in sp_track['artists']])}\n"
            )
            print(t.error(f" could not find the track '{song404[-1]}'"))
    Files.NOT_FOUND.save(''.join(not_found) + '\n')

def pick_td_playlist_for_sp_playlist(
    sp_playlist, td_playlists: Mapping[str, tidalapi.Playlist]
):
    if sp_playlist["name"] in td_playlists:
        # get tidal playlist with same name
        td_playlist = td_playlists[sp_playlist["name"]]
        return (sp_playlist, td_playlist)
    else:
        return (sp_playlist, None)
