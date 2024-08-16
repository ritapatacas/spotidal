import asyncio
import datetime
import tidalapi
import utils
import td_fetch
import sp_fetch as _sp_fetch
from typing import Sequence, Mapping
from tqdm.asyncio import tqdm as atqdm
import sp_types
from cache import failure_cache, track_match_cache


def save_playlists_to_json(playlists):
    utils.save_to_json(playlists, 'user_data/tidal_playlists.json')
    return playlists

async def fetch_playlists(tidal_session: tidalapi.Session):
    playlists = await get_tidal_playlists_wrapper(tidal_session)
    result = []
    for p in playlists:
        parsed_playlist = playlist_to_dict(p)
        result.append(parsed_playlist)

    return result

async def fetch_and_save_playlists(tidal_session: tidalapi.Session):
    playlists = await fetch_playlists(tidal_session)

    save_playlists_to_json(playlists)
    return playlists

#### from sync on git@github.com:spotify2tidal/spotify_to_tidal.git

async def tidal_search(spotify_track, rate_limiter, tidal_session: tidalapi.Session) -> tidalapi.Track | None:
    def _search_for_track_in_album():
        # search for album name and first album artist
        if 'album' in spotify_track and 'artists' in spotify_track['album'] and len(spotify_track['album']['artists']):
            query = utils.simple(spotify_track['album']['name']) + " " + utils.simple(spotify_track['album']['artists'][0]['name'])
            album_result = tidal_session.search(query, models=[tidalapi.album.Album])
            for album in album_result['albums']:
                if album.num_tracks >= spotify_track['track_number'] and utils.test_album_similarity(spotify_track['album'], album):
                    album_tracks = album.tracks()
                    if len(album_tracks) < spotify_track['track_number']:
                        assert( not len(album_tracks) == album.num_tracks ) # incorrect metadata :(
                        continue
                    track = album_tracks[spotify_track['track_number'] - 1]
                    if utils.match(track, spotify_track):
                        failure_cache.remove_match_failure(spotify_track['id'])
                        return track

    def _search_for_standalone_track():
        # if album search fails then search for track name and first artist
        query = utils.simple(spotify_track['name']) + ' ' + utils.simple(spotify_track['artists'][0]['name'])
        for track in tidal_session.search(query, models=[tidalapi.media.Track])['tracks']:
            if utils.match(track, spotify_track):
                failure_cache.remove_match_failure(spotify_track['id'])
                return track
    await rate_limiter.acquire()
    album_search = await asyncio.to_thread( _search_for_track_in_album )
    if album_search:
        return album_search
    await rate_limiter.acquire()
    track_search = await asyncio.to_thread( _search_for_standalone_track )
    if track_search:
        return track_search

    # if none of the search modes succeeded then store the track id to the failure cache
    failure_cache.cache_match_failure(spotify_track['id'])

async def search_new_tracks_on_tidal(tidal_session: tidalapi.Session, spotify_tracks: Sequence[sp_types.SpotifyTrack], playlist_name: str, config: dict):
    """ Generic function for searching for each item in a list of Spotify tracks which have not already been seen and adding them to the cache """
    async def _run_rate_limiter(semaphore):
        ''' Leaky bucket algorithm for rate limiting. Periodically releases items from semaphore at rate_limit'''
        _sleep_time = config.get('max_concurrency', 10)/config.get('rate_limit', 10)/4 # aim to sleep approx time to drain 1/4 of 'bucket'
        t0 = datetime.datetime.now()
        while True:
            await asyncio.sleep(_sleep_time)
            t = datetime.datetime.now()
            dt = (t - t0).total_seconds()
            new_items = round(config.get('rate_limit', 10)*dt)
            t0 = t
            [semaphore.release() for i in range(new_items)] # leak new_items from the 'bucket'

    # Extract the new tracks that do not already exist in the old tidal tracklist
    tracks_to_search = _sp_fetch.get_new_spotify_tracks(spotify_tracks)
    if not tracks_to_search:
        return

    # Search for each of the tracks on Tidal concurrently
    task_description = " > Searching Tidal for {}/{} tracks in Spotify playlist '{}'".format(len(tracks_to_search), len(spotify_tracks), playlist_name)
    semaphore = asyncio.Semaphore(config.get('max_concurrency', 10))
    rate_limiter_task = asyncio.create_task(_run_rate_limiter(semaphore))
    search_results = await atqdm.gather( *[ utils.repeat_on_request_error(tidal_search, t, semaphore, tidal_session) for t in tracks_to_search ], desc=task_description )
    rate_limiter_task.cancel()

    # Add the search results to the cache
    for idx, spotify_track in enumerate(tracks_to_search):
        if search_results[idx]:
            track_match_cache.insert( (spotify_track['id'], search_results[idx].id) )
        else:
            color = ('\033[91m', '\033[0m')
            print(color[0] + f" > Could not find track {spotify_track['id']}: {','.join([a['name'] for a in spotify_track['artists']])} - {spotify_track['name']}" + color[1])

async def get_tidal_playlists_wrapper(tidal_session: tidalapi.Session):
    tidal_playlists = await td_fetch.get_all_playlists(tidal_session.user)

    return tidal_playlists

def pick_tidal_playlist_for_spotify_playlist(sp_p, td_playlists: Mapping[str, tidalapi.Playlist]):
    for td_p in td_playlists:
        if sp_p['name'] == td_p['name']:
            #print('\ntdp ', td_p.name, td_p.id)
            #print('dpp ', sp_playlist['name'], sp_playlist['id'])
            return (sp_p['id'], td_p['id'])
    return (sp_p['id'], None)

####


def playlist_to_dict(playlist: tidalapi.Playlist):
        return {
            "name": playlist.name,
            "id": playlist.id,
            "data": {
                "num_tracks": playlist.num_tracks,
                "num_videos": playlist.num_videos,
                "creator": str(playlist.creator) if playlist.creator else None,
                "description": playlist.description,
                "duration": playlist.duration,
                "last_updated": playlist.last_updated.isoformat() if playlist.last_updated else None,
                "created": playlist.created.isoformat() if playlist.created else None,
                "type": playlist.type,
                "public": playlist.public,
                "popularity": playlist.popularity,
                "promoted_artists": [str(artist) for artist in playlist.promoted_artists] if playlist.promoted_artists else None,
                "last_item_added_at": playlist.last_item_added_at.isoformat() if playlist.last_item_added_at else None,
                "picture": playlist.picture,
                "square_picture": playlist.square_picture,
                "user_date_added": playlist.user_date_added.isoformat() if playlist.user_date_added else None,
                "_etag": playlist._etag
            }
        }
