import json
import sys
import asyncio
import utils
import auth as _auth
import sp_fetch as _sp_fetch
import td_utils as _td_utils
import parse_sp_td as _parse_sp_td
import sp_spy as _sp_spy

sessions = None
sp = None
td = None

async def main():
    global sp, td
    utils.header()
    sessions = _auth.main()
    sp = sessions['sp']
    td = sessions['td']


    playlist_id = "ef2426e6-4530-4d89-9282-59a36e0edfb2"
    print(_td_utils.get_playlist_by_id(td, playlist_id))


    #pl = td.playlist('ef2426e6-4530-4d89-9282-59a36e0edfb2')

    #await _parse_sp_td.fetch_and_save_playlists(sessions)

    #playlists = _parse_sp_td.load_playlists_from_json()
    #print(len(playlists['sp']), len(playlists['td']))
    #matches = await _parse_sp_td.find_matching_playlists(playlists)

    #_parse_sp_td.sync_playlist(sessions)

    #_td_utils.get_all_playlist_tracks()











if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)
