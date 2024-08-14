import json
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

    mapping = await _parse_sp_td.get_user_playlist_mappings(sp, td)
"""
    for m in mapping:
        print(json.dumps(m, indent=4)) """


if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)
