from typing import List, Sequence
import tidalapi
from spotidal.src.model.helpers.cache import failure_cache, track_match_cache
from spotidal.src.model.helpers.type import spotify as t_spotify
from spotidal.src.view.text import Text as txt
import spotidal.src.model.helpers.sync.match as _match


def populate_track_match_cache(
    sp_tracks_: Sequence[t_spotify.SpotifyTrack],
    td_tracks_: Sequence[tidalapi.Track],
):
    """Populate the track match cache with all the existing tracks in Tidal playlist corresponding to Spotify playlist"""

    def _populate_one_track_from_sp(spotify_track: t_spotify.SpotifyTrack):
        for idx, td_track in list(enumerate(td_tracks)):
            if td_track.available and _match.match(td_track, spotify_track):
                track_match_cache.insert((spotify_track["id"], td_track.id))
                td_tracks.pop(idx)
                return

    def _populate_one_track_from_td(td_track: tidalapi.Track):
        for idx, spotify_track in list(enumerate(sp_tracks)):
            if td_track.available and _match.match(td_track, spotify_track):
                track_match_cache.insert((spotify_track["id"], td_track.id))
                sp_tracks.pop(idx)
                return

    # make a copy of the tracks to avoid modifying original arrays
    sp_tracks = [t for t in sp_tracks_]
    td_tracks = [t for t in td_tracks_]

    # first populate from the tidal tracks
    for track in td_tracks:
        _populate_one_track_from_td(track)
    # then populate from the subset of Spotify tracks that didn't match (to account for many-to-one style mappings)
    for track in sp_tracks:
        _populate_one_track_from_sp(track)


def get_new_sp_tracks(
    sp_tracks: Sequence[t_spotify.SpotifyTrack],
) -> List[t_spotify.SpotifyTrack]:
    """Extracts only the tracks that have not already been seen in our Tidal caches"""
    results = []
    for spotify_track in sp_tracks:
        if not spotify_track["id"]:
            continue
        if not track_match_cache.get(
            spotify_track["id"]
        ) and not failure_cache.has_match_failure(spotify_track["id"]):
            results.append(spotify_track)
    return results


def get_tracks_for_new_td_playlist(
    sp_tracks: Sequence[t_spotify.SpotifyTrack],
) -> Sequence[int]:
    """gets list of corresponding tidal track ids for each spotify track, ignoring duplicates"""
    output = []
    seen_tracks = set()

    for t in sp_tracks:
        if not t["id"]:
            continue
        td_id = track_match_cache.get(t["id"])
        if td_id:
            if td_id in seen_tracks:
                track_name = t["name"]
                artist_names = ", ".join(
                    [artist["name"] for artist in t["artists"]]
                )
                print(
                    txt.error(
                        f"'{track_name}', '{artist_names}' is duplicate and will be ignored"
                    )
                )
            else:
                output.append(td_id)
                seen_tracks.add(td_id)
    return output
