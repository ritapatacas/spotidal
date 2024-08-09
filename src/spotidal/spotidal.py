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

    _sp_fetch.fetch_and_save_spotify_playlists(sp)
    playlists = await _td_fetch.get_all_playlists(td.user)




"""
def fetch_and_save_spotify_playlists():
    session = _sp_fetch.main()
    playlists = _sp_fetch.get_playlists_names_ids(session)
    _sp_fetch.save_spotify_playlists_to_json(playlists) """

if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)
