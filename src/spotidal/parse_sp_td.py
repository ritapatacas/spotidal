import asyncio
from typing import List
import utils
import tidalapi
import spotipy
import td_fetch as _td_fetch
import sp_fetch as _sp_fetch
import td_utils as _td_utils
from cache import track_match_cache
from tqdm import tqdm


async def fetch_playlists(sessions):
    playlists = {
        'sp': _sp_fetch.get_playlists_names_ids(sessions['sp']),
        'td': await _td_fetch.get_playlists_names_ids(sessions['td'])
    }
    return playlists

async def save_playlists_to_json(playlists):
    print("\n\n> Saving playlists to json")
    utils.save_to_json(playlists['sp'], 'user_data/spotify_playlists.json')
    utils.save_to_json(playlists['td'], 'user_data/tidal_playlists.json')

    # matches = await find_matching_playlists(sp_playlists, td_playlists)

def load_playlists_from_json():
    playlists = {
        'sp': utils.load_playlists_from_json('user_data/spotify_playlists.json'),
        'td': utils.load_playlists_from_json('user_data/tidal_playlists.json')
    }
    return playlists

async def fetch_and_save_playlists(sessions):
    playlists = await fetch_playlists(sessions)
    await save_playlists_to_json(playlists)

async def find_matching_playlists(playlists):
    matches = []

    sp_playlists = playlists['sp']
    td_playlists = playlists['td']

    print(
        f"\n\n> Looking for matches for {len(sp_playlists)} spotify playlists\n")

    for sp_playlist in sp_playlists:
        for td_playlist in td_playlists:
            if sp_playlist['name'] == td_playlist['name']:
                matches.append({sp_playlist['name']: {'sp': sp_playlist['id'], 'td': td_playlist['id'], 'sync': sp_playlist['sync']}})
                print(f"    Match! {sp_playlist['name']}")
                break
    print(f"\n> Found: {len(matches)}")
    utils.save_to_json(matches, 'user_data/matching_playlists.json')
    return matches






#### from sync on git@github.com:spotify2tidal/spotify_to_tidal.git
async def get_user_playlist_mappings(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session):
    results = []
    spotify_playlists = await _sp_fetch.get_playlists_from_spotify(spotify_session)
    tidal_playlists = await _td_utils.get_tidal_playlists_wrapper(tidal_session)
    for playlist in tidal_playlists:
        print('\n\nname ', playlist.name)

    for spotify_playlist in spotify_playlists:
        td_playlist = _td_utils.pick_tidal_playlist_for_spotify_playlist(spotify_playlist, tidal_playlists)
        results.append(td_playlist)
        #print('\n\n td name is', td_playlist)
    return results

async def sync_playlist(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, spotify_playlist, tidal_playlist: tidalapi.Playlist | None, config: dict):
    """ sync given playlist to tidal """
    # Create a new Tidal playlist if required
    if not tidal_playlist:
        print(f"No playlist found on Tidal corresponding to Spotify playlist: '{spotify_playlist['name']}', creating new playlist")
        tidal_playlist =  tidal_session.user.create_playlist(spotify_playlist['name'], spotify_playlist['description'])

    # Extract the new tracks from the playlist that we haven't already seen before
    spotify_tracks = await _sp_fetch.get_tracks_from_spotify_playlist(spotify_session, spotify_playlist)
    old_tidal_tracks = await _td_fetch.get_all_playlist_tracks(tidal_playlist)
    utils.populate_track_match_cache(spotify_tracks, old_tidal_tracks)
    await _td_utils.search_new_tracks_on_tidal(tidal_session, spotify_tracks, spotify_playlist['name'], config)
    new_tidal_track_ids = _sp_fetch.get_tracks_for_new_tidal_playlist(spotify_tracks)

    # Update the Tidal playlist if there are changes
    old_tidal_track_ids = [t.id for t in old_tidal_tracks]
    if new_tidal_track_ids == old_tidal_track_ids:
        print("No changes to write to Tidal playlist")
    elif new_tidal_track_ids[:len(old_tidal_track_ids)] == old_tidal_track_ids:
        # Append new tracks to the existing playlist if possible
        _td_fetch.add_multiple_tracks_to_playlist(tidal_playlist, new_tidal_track_ids[len(old_tidal_track_ids):])
    else:
        # Erase old playlist and add new tracks from scratch if any reordering occured
        _td_fetch.clear_tidal_playlist(tidal_playlist)
        _td_fetch.add_multiple_tracks_to_playlist(tidal_playlist, new_tidal_track_ids)

async def sync_favorites(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, config: dict):
    """ sync user favorites to tidal """
    async def get_tracks_from_spotify_favorites() -> List[dict]:
        _get_favorite_tracks = lambda offset: spotify_session.current_user_saved_tracks(offset=offset)
        tracks = await _sp_fetch._fetch_all_from_spotify_in_chunks(_get_favorite_tracks)
        tracks.reverse()
        return tracks

    def get_new_tidal_favorites() -> List[int]:
        existing_favorite_ids = set([track.id for track in old_tidal_tracks])
        new_ids = []
        for spotify_track in spotify_tracks:
            match_id = track_match_cache.get(spotify_track['id'])
            if match_id and not match_id in existing_favorite_ids:
                new_ids.append(match_id)
        return new_ids

    print("Loading favorite tracks from Spotify")
    spotify_tracks = await get_tracks_from_spotify_favorites()
    print("Loading existing favorite tracks from Tidal")
    old_tidal_tracks = await _td_fetch.get_all_favorites(tidal_session.user.favorites, order='DATE')
    utils.populate_track_match_cache(spotify_tracks, old_tidal_tracks)
    await _td_utils.search_new_tracks_on_tidal(tidal_session, spotify_tracks, "Favorites", config)
    new_tidal_favorite_ids = get_new_tidal_favorites()
    if new_tidal_favorite_ids:
        for tidal_id in tqdm(new_tidal_favorite_ids, desc="Adding new tracks to Tidal favorites"):
            tidal_session.user.favorites.add_track(tidal_id)
    else:
        print("No new tracks to add to Tidal favorites")

def sync_playlists_wrapper(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, playlists, config: dict):
  for spotify_playlist, tidal_playlist in playlists:
    # sync the spotify playlist to tidal
    asyncio.run(sync_playlist(spotify_session, tidal_session, spotify_playlist, tidal_playlist, config) )

def sync_favorites_wrapper(spotify_session: spotipy.Spotify, tidal_session: tidalapi.Session, config):
    asyncio.run(main=sync_favorites(spotify_session=spotify_session, tidal_session=tidal_session, config=config))
