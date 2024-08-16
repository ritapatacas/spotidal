import utils
import spotipy
import sp_fetch as _sp_fetch

def save_playlists_to_json(playlists):
    utils.save_to_json(playlists, 'user_data/spotify_playlists.json')
    return playlists

async def fetch_and_save_playlists(session: spotipy.Spotify):
    playlists = await fetch_playlists(session)
    result = []
    for p in playlists:
        parsed_playlist = playlist_to_dict(p)
        result.append(parsed_playlist)
    save_playlists_to_json(result)
    return result

async def fetch_playlists(session: spotipy.Spotify):
    return await _sp_fetch.get_playlists_from_spotify(session)

def playlist_to_dict(playlist):
        return {
            "name": playlist['name'],
            "id": playlist['id'],
            "data": playlist
        }
