from difflib import SequenceMatcher
from typing import Sequence, Set
import tidalapi
import unicodedata
from spotidal.src.model.helpers.type import spotify as t_spotify


def normalize(s) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")

def simple(str: str) -> str:
    # only take the first part of a string before any hyphens or brackets to account for different versions
    return (
        str.split("-")[0].strip().split("(")[0].strip().split("[")[0].strip()
    )

def isrc_match(td_track: tidalapi.Track, sp_track) -> bool:
    if "isrc" in sp_track["external_ids"]:
        return td_track.isrc == sp_track["external_ids"]["isrc"]
    return False

def duration_match(td_track: tidalapi.Track, sp_track, tolerance=2) -> bool:
    # the duration of the two tracks must be the same to within 2 seconds
    return abs(td_track.duration - sp_track["duration_ms"] / 1000) < tolerance

def name_match(td_track, sp_track) -> bool:
    def exclusion_rule(
        pattern: str, td_track: tidalapi.Track, sp_track: t_spotify.SpotifyTrack
    ):
        spotify_has_pattern = pattern in sp_track["name"].lower()
        tidal_has_pattern = pattern in td_track.name.lower() or (
            not td_track.version is None and (pattern in td_track.version.lower())
        )
        return spotify_has_pattern != tidal_has_pattern

    # handle some edge cases
    if exclusion_rule("instrumental", td_track, sp_track):
        return False
    if exclusion_rule("acapella", td_track, sp_track):
        return False
    if exclusion_rule("remix", td_track, sp_track):
        return False

    # the simplified version of the Spotify track name must be a substring of the Tidal track name
    # Try with both un-normalized and then normalized
    simple_spotify_track = (
        simple(sp_track["name"].lower()).split("feat.")[0].strip()
    )
    return simple_spotify_track in td_track.name.lower() or normalize(
        simple_spotify_track
    ) in normalize(td_track.name.lower())

def artist_match(td: tidalapi.Track | tidalapi.Album, sp) -> bool:
    def split_artist_name(artist: str) -> Sequence[str]:
        if "&" in artist:
            return artist.split("&")
        elif "," in artist:
            return artist.split(",")
        else:
            return [artist]

    def get_td_artists(
        td: tidalapi.Track | tidalapi.Album, do_normalize=False
    ) -> Set[str]:
        result: list[str] = []
        for artist in td.artists:
            if do_normalize:
                artist_name = normalize(artist.name)
            else:
                artist_name = artist.name
            result.extend(split_artist_name(artist_name))
        return set([simple(x.strip().lower()) for x in result])

    def get_sp_artists(sp, do_normalize=False) -> Set[str]:
        result: list[str] = []
        for artist in sp["artists"]:
            if do_normalize:
                artist_name = normalize(artist["name"])
            else:
                artist_name = artist["name"]
            result.extend(split_artist_name(artist_name))
        return set([simple(x.strip().lower()) for x in result])

    # There must be at least one overlapping artist between the Tidal and Spotify track
    # Try with both un-normalized and then normalized
    if get_td_artists(td).intersection(get_sp_artists(sp)) != set():
        return True
    return (
        get_td_artists(td, True).intersection(get_sp_artists(sp, True))
        != set()
    )

def match(td_track, sp_track) -> bool:
    if not sp_track["id"]:
        return False
    return isrc_match(td_track, sp_track) or (
        duration_match(td_track, sp_track)
        and name_match(td_track, sp_track)
        and artist_match(td_track, sp_track)
    )

def test_album_similarity(sp_album, td_album, threshold=0.6):
    return SequenceMatcher(
        None, simple(sp_album["name"]), simple(td_album.name)
    ).ratio() >= threshold and artist_match(td_album, sp_album)
