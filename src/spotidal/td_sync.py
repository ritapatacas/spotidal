import tidalapi
import auth_td as _auth_td


#if there is no tidal_playlist:
def create_new_playlist(playlist):
        td = _auth_td.get_session()
        print(f" > No playlist found on Tidal with name: '{playlist['name']}', creating new playlist")
        return td.user.create_playlist(playlist['name'], "")



# Extract the new tracks from the playlist that we haven't already seen before
spotify_tracks = await get_tracks_from_spotify_playlist(spotify_session, spotify_playlist)
old_tidal_tracks = await get_all_playlist_tracks(tidal_playlist)
populate_track_match_cache(spotify_tracks, old_tidal_tracks)
await search_new_tracks_on_tidal(tidal_session, spotify_tracks, spotify_playlist['name'], config)
new_tidal_track_ids = get_tracks_for_new_tidal_playlist(spotify_tracks)
