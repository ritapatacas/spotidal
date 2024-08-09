import os
import sys
import json
import auth as _auth
import sp_fetch as _sp_fetch


def main():
    print("SPOTIDAL\n\n")
    sessions = _auth.main()
    print(sessions)


"""
def fetch_and_save_spotify_playlists():
    session = _sp_fetch.main()
    playlists = _sp_fetch.get_playlists_names_ids(session)
    _sp_fetch.save_spotify_playlists_to_json(playlists) """

if __name__ == '__main__':
    main()
    sys.exit(0)
