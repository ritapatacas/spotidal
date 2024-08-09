import sys
import asyncio
import utils
import auth as _auth
import sp_fetch as _sp_fetch
import td_fetch as _td_fetch
import parse_sp_td as _parse_sp_td

sessions = None
sp = None
td = None

async def main():
    global sp, td
    utils.header()
    sessions = _auth.main()
    sp = sessions['sp']
    td = sessions['td']

#    await _parse_sp_td.fetch_playlists(sp, td)

    #await _parse_sp_td.fetch_and_save_playlists(sessions)

    playlists = _parse_sp_td.load_playlists_from_json()
    print(len(playlists['sp']), len(playlists['td']))
    matches = await _parse_sp_td.find_matching_playlists(playlists)



async def find_matching_playlists(sp_playlists, tidal_playlists):
    matches = []

    print(f"\n\n> Looking for matches for {len(sp_playlists)} spotify playlists\n")

    for sp_playlist in sp_playlists:
        tidal_playlist = await  _td_fetch.pick_tidal_playlist_for_spotify_playlist(sp_playlist['name'], tidal_playlists)
        if tidal_playlist:
            matches.append((sp_playlist, tidal_playlist))
            print(f"    Match! {sp_playlist['name']}")
    print(f"\n> Found: {len(matches)}")
    return matches





"""
def fetch_and_save_spotify_playlists():
    session = _sp_fetch.main()
    playlists = _sp_fetch.get_playlists_names_ids(session)
    _sp_fetch.save_spotify_playlists_to_json(playlists) """

if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)
