import os
import sys
import json
import auth_sp as _sp_auth
import auth_td as _td_auth
import sp_fetch as _sp_fetch


def main():
    print("Getting sessions\n")

    session = {
        'sp': _sp_auth.get_session(),
        'td': _td_auth.get_session()
    }
    return session


if __name__ == '__main__':
    main()
    sys.exit(0)
