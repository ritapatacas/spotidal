import json
import sys
import asyncio
import utils
import auth as _auth
import sp_utils as _sp_utils
import td_utils as _td_utils
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

    await _parse_sp_td.fetch_and_map_playlists(sp, td)
    await _parse_sp_td.sync_from_map(sp, td)


if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)
