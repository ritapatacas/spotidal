import asyncio
import datetime
from typing import Sequence, Mapping
import tidalapi
from tqdm.asyncio import tqdm as atqdm

from ..cache import failure_cache, track_match_cache
from ..type import spotify as t_spotify
from ..type.file import Files
from ....view.text import Text as t

from ..sync import match as _match
from ..sync import musicbrainz as _musicbrainz
from . import cache as _cache
from . import request_utils as _req

_NOT_FOUND_TRACKS = []
_ORIGINAL_ALBUM_CHOICES = []


def pop_not_found_tracks():
    tracks = list(_NOT_FOUND_TRACKS)
    _NOT_FOUND_TRACKS.clear()
    return tracks


def pop_original_album_choices():
    """Tracks where the Spotify-reported album differs from the track's
    genuine original studio album (per MusicBrainz), and TIDAL has both as
    distinct options — deferred rather than decided silently. Each entry:
    {"sp_track", "playlist_name", "spotify_track", "original_track",
    "original_album_name"}."""
    choices = list(_ORIGINAL_ALBUM_CHOICES)
    _ORIGINAL_ALBUM_CHOICES.clear()
    return choices


async def td_search(
    sp_track, rate_limiter, td_session: tidalapi.Session, playlist_name: str = ""
) -> tidalapi.Track | None:
    def _search_for_track_in_album(album_name, album_artist, match_fn=_match.match):
        # search a specific album by name (not necessarily sp_track's own
        # reported album — see the MusicBrainz-original-album path below)
        # for the track matching sp_track, by title rather than position:
        # track_number is only meaningful relative to sp_track's own album.
        query = _match.simple(album_name) + " " + _match.simple(album_artist)
        album_result = td_session.search(query, models=[tidalapi.album.Album])
        fake_sp_album = {"name": album_name, "artists": [{"name": album_artist}]}
        for album in album_result["albums"]:
            if not _match.test_album_similarity(fake_sp_album, album):
                continue
            for track in album.tracks():
                if match_fn(track, sp_track):
                    return track

    def _search_for_track_in_sp_album(match_fn=_match.match):
        # search for sp_track's own reported album name and first album artist
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
                    if match_fn(track, sp_track):
                        return track

    def _search_for_standalone_track(match_fn=_match.match):
        # if album search fails then search for track name and first artist
        query = (
            _match.simple(sp_track["name"])
            + " "
            + _match.simple(sp_track["artists"][0]["name"])
        )
        for track in td_session.search(query, models=[tidalapi.media.Track])[
            "tracks"
        ]:
            if match_fn(track, sp_track):
                return track

    def _musicbrainz_original_album_name():
        isrc = sp_track.get("external_ids", {}).get("isrc")
        return _musicbrainz.original_album_name(isrc)

    # Ask MusicBrainz up front whether sp_track's own reported album is
    # actually the original studio release, or a compilation/reissue —
    # Spotify (and TIDAL) both serve compilation copies of well-known
    # tracks constantly, so this can't be told from the Spotify data alone.
    original_album_name = await asyncio.to_thread(_musicbrainz_original_album_name)
    sp_album_name = sp_track.get("album", {}).get("name")
    needs_choice = bool(
        original_album_name and sp_album_name
        and _match.simple(original_album_name).lower() != _match.simple(sp_album_name).lower()
    )

    # Plan A/B: strict match (ISRC, or exact duration+name+artist) against
    # sp_track's own reported album, then a standalone track search. Plan
    # C/D: same order, but with a looser match (wider duration tolerance,
    # and an artist splitter that also recognizes "feat."/"×"/"and" as
    # separators) — a manual spot check found this recovers a large share
    # of tracks the strict pass rejects only over text-formatting
    # differences, not because the matching TIDAL track doesn't exist.
    spotify_result = None
    for match_fn in (_match.match, _match.loose_match):
        await rate_limiter.acquire()
        album_search = await asyncio.to_thread(_search_for_track_in_sp_album, match_fn)
        if album_search:
            spotify_result = album_search
            break
        await rate_limiter.acquire()
        track_search = await asyncio.to_thread(_search_for_standalone_track, match_fn)
        if track_search:
            spotify_result = track_search
            break

    if not needs_choice:
        if spotify_result:
            failure_cache.remove_match_failure(sp_track["id"])
        else:
            failure_cache.cache_match_failure(sp_track["id"])
        return spotify_result

    await rate_limiter.acquire()
    original_result = await asyncio.to_thread(
        _search_for_track_in_album, original_album_name, sp_track["artists"][0]["name"]
    )

    if original_result and spotify_result and original_result.id != spotify_result.id:
        # Both exist as distinct TIDAL tracks — don't silently pick one;
        # defer to the end-of-job review (see search.pop_original_album_choices).
        _ORIGINAL_ALBUM_CHOICES.append({
            "sp_track": sp_track,
            "playlist_name": playlist_name,
            "spotify_track": spotify_result,
            "original_track": original_result,
            "original_album_name": original_album_name,
        })
        failure_cache.remove_match_failure(sp_track["id"])
        return spotify_result  # default until/unless the review swaps it

    result = original_result or spotify_result
    if result:
        failure_cache.remove_match_failure(sp_track["id"])
    else:
        failure_cache.cache_match_failure(sp_track["id"])
    return result

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
        "searching tidal for {}/{} tracks in spotify playlist '{}'".format(
            len(tracks_to_search), len(sp_tracks), playlist_name
        )
    )
    semaphore = asyncio.Semaphore(config.get("max_concurrency", 10))
    rate_limiter_task = asyncio.create_task(_run_rate_limiter(semaphore))
    search_results = await atqdm.gather(
        *[
            _req.repeat_on_request_error(
                td_search, t, semaphore, td_session, playlist_name
            )
            for t in tracks_to_search
        ],
        desc=t.busy(task_description),
    )
    rate_limiter_task.cancel()

    # todo song404 is for future use with track id to repeat search
    songs404 = []
        
    for idx, sp_track in enumerate(tracks_to_search):
        if search_results[idx]:
            track_match_cache.insert((sp_track["id"], search_results[idx].id))
        else:
            track_dict = {
                "sp_id": sp_track["id"],
                "track": {
                    "name": sp_track["name"],
                    "artists": f"{','.join([a['name'] for a in sp_track['artists']])}",
                    "album": sp_track["album"]["name"],
                    "track_number": sp_track["track_number"],
                }
            }

            songs404.append(track_dict)
            _NOT_FOUND_TRACKS.append(
                f"{track_dict['track']['name']} {track_dict['track']['artists']}"
            )

    if songs404.__len__() > 0:
        Files.NOT_FOUND.save(songs404, playlist_name)

def pick_td_playlist_for_sp_playlist(
    sp_playlist, td_playlists: Mapping[str, tidalapi.Playlist]
):
    if sp_playlist["name"] in td_playlists:
        # get tidal playlist with same name
        td_playlist = td_playlists[sp_playlist["name"]]
        return (sp_playlist, td_playlist)
    else:
        return (sp_playlist, None)
