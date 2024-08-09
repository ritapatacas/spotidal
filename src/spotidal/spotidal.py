import sys
import asyncio
import auth as _auth
import sp_fetch as _sp_fetch
import td_fetch as _td_fetch

sp = None
td = None

async def main():
    global sp, td
    print("SPOTIDAL\n\n")
    sessions = _auth.main()
    sp = sessions['sp']
    td = sessions['td']

    #_sp_fetch.fetch_and_save_spotify_playlists(sp)
    playlists = await _td_fetch.get_tidal_playlists_wrapper(td)

    sp_playlists = _sp_fetch.get_playlists_names_ids(sp)
    tidal_playlists = await _td_fetch.get_tidal_playlists_wrapper(td)

    matches = await find_matching_playlists(sp_playlists, tidal_playlists)

    for sp_playlist, tidal_playlist in matches:
        print(f"Match found! Spotify Playlist: {sp_playlist['name']}, Tidal Playlist: {tidal_playlist.name}")




async def find_matching_playlists(sp_playlists, tidal_playlists):
    matches = []

    for sp_playlist in sp_playlists:
        tidal_playlist = await  _td_fetch.pick_tidal_playlist_for_spotify_playlist(sp_playlist['name'], tidal_playlists)
        if tidal_playlist:
            matches.append((sp_playlist, tidal_playlist))

    return matches





"""
def fetch_and_save_spotify_playlists():
    session = _sp_fetch.main()
    playlists = _sp_fetch.get_playlists_names_ids(session)
    _sp_fetch.save_spotify_playlists_to_json(playlists) """

if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)
