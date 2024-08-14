import math
import json
import utils
import asyncio
import spotipy
import spotipy.util as util
import sp_types
from auth_sp import get_username
from tqdm.asyncio import tqdm as atqdm
from typing import Callable, List, Sequence
from cache import failure_cache, track_match_cache


def show_tracks(tracks):
    for i, item in enumerate(tracks['items']):
        track = item['track']
        print("   %d %32.32s %s" % (i, track['artists'][0]['name'],
            track['name']))

def get_playlists_names_ids(session):
    playlists_data = session.current_user_playlists()
    print("> Fetching Spotify playlists")
    print(f" > Total spotify playlists: {playlists_data['total']}")
    playlists = [{"id": playlist['id'], "name": playlist['name'], 'sync': 'off' } for playlist in playlists_data['items']]

    #for p in playlists:
    #    print(f"    {p['id']}  {p['name']}")

    return playlists

def get_playlists_details(session):
    username = session.current_user()['id']
    token = util.prompt_for_user_token(username)

    if token:
        playlists = session.user_playlists(username)
        for playlist in playlists['items']:
            if playlist['owner']['id'] == username:
                print()
                print(playlist['name'])
                print ('  total tracks', playlist['tracks']['total'])
                results = session.playlist(playlist['id'],
                    fields="tracks,next")
                tracks = results['tracks']
                show_tracks(tracks)
                while tracks['next']:
                    tracks = session.next(tracks)
                    show_tracks(tracks)
    else:
        print("Can't get token for", username)


def save_playlists_to_json(playlists):
    file = utils.get_file_path('user_data/spotify_playlists.json')

    with open(file, 'w') as file:
        json.dump(playlists, file, indent=4)

    print("\n > Saved to user_data/spotify_playlists.json")


def fetch_and_save_spotify_playlists(session):
    playlists = get_playlists_names_ids(session)
    save_playlists_to_json(playlists)


#### from sync on git@github.com:spotify2tidal/spotify_to_tidal.git

async def _fetch_all_from_spotify_in_chunks(fetch_function: Callable) -> List[dict]:
    output = []
    results = fetch_function(0)
    output.extend([item['track'] for item in results['items'] if item['track'] is not None])

    # Get all the remaining tracks in parallel
    if results['next']:
        offsets = [results['limit'] * n for n in range(1, math.ceil(results['total'] / results['limit']))]
        extra_results = await atqdm.gather(
            *[asyncio.to_thread(fetch_function, offset) for offset in offsets],
            desc="Fetching additional data chunks"
        )
        for extra_result in extra_results:
            output.extend([item['track'] for item in extra_result['items'] if item['track'] is not None])

    return output

async def get_tracks_from_spotify_playlist(spotify_session: spotipy.Spotify, spotify_playlist):
    def _get_tracks_from_spotify_playlist(offset: int, spotify_session: spotipy.Spotify, playlist_id: str):
        fields = "next,total,limit,items(track(name,album(name,artists),artists,track_number,duration_ms,id,external_ids(isrc)))"
        return spotify_session.playlist_tracks(playlist_id=playlist_id, fields=fields, offset=offset)

    print(f"Loading tracks from Spotify playlist '{spotify_playlist['name']}'")
    return await _fetch_all_from_spotify_in_chunks(lambda offset, session=spotify_session: _get_tracks_from_spotify_playlist(offset=offset, spotify_session=session, playlist_id=spotify_playlist["id"]))

async def get_playlists_from_spotify(spotify_session: spotipy.Spotify):
    # get all the user playlists from the Spotify account
    playlists = []
    username = get_username()

    print("Loading Spotify playlists")
    results = spotify_session.user_playlists(username)
    print('results', len(results))
    playlists.extend([p for p in results['items']])
    print('p1', len(playlists))

    # get all the remaining playlists in parallel
    if results['next']:
        offsets = [ results['limit'] * n for n in range(1, math.ceil(results['total']/results['limit'])) ]
        extra_results = await atqdm.gather( *[asyncio.to_thread(spotify_session.user_playlists, username, offset=offset) for offset in offsets ] )
        for extra_result in extra_results:
            playlists.extend([p for p in extra_result['items'] if p['owner']['id'] == username])
        print('p2', len(playlists))
    return playlists

def get_new_spotify_tracks(spotify_tracks: Sequence[sp_types.SpotifyTrack]) -> List[sp_types.SpotifyTrack]:
    ''' Extracts only the tracks that have not already been seen in our Tidal caches '''
    results = []
    for spotify_track in spotify_tracks:
        if not spotify_track['id']: continue
        if not track_match_cache.get(spotify_track['id']) and not failure_cache.has_match_failure(spotify_track['id']):
            results.append(spotify_track)
    return results

def get_tracks_for_new_tidal_playlist(spotify_tracks: Sequence[sp_types.SpotifyTrack]) -> Sequence[int]:
    ''' gets list of corresponding tidal track ids for each spotify track, ignoring duplicates '''
    output = []
    seen_tracks = set()

    for spotify_track in spotify_tracks:
        if not spotify_track['id']: continue
        tidal_id = track_match_cache.get(spotify_track['id'])
        if tidal_id:
            if tidal_id in seen_tracks:
                track_name = spotify_track['name']
                artist_names = ', '.join([artist['name'] for artist in spotify_track['artists']])
                print(f'Duplicate found: Track "{track_name}" by {artist_names} will be ignored')
            else:
                output.append(tidal_id)
                seen_tracks.add(tidal_id)
    return output



###
