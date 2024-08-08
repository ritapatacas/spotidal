import os
import sys
import json
import sp_auth as _sp_auth


def main():
    spotify_session = _sp_auth.open_session()

    playlists = get_spotify_playlists(spotify_session)
    save_spotify_playlists_to_json (playlists)

def get_spotify_playlists(spotify_session):
    playlists_data = spotify_session.current_user_playlists()
    print(f"Total Playlists: {playlists_data['total']}")
    playlists = [{"id": playlist['id'], "name": playlist['name'], 'sync': 'off' } for playlist in playlists_data['items']]

    for p in playlists:
        print(f"{p['id']}  {p['name']}")

    return playlists

def save_spotify_playlists_to_json(playlists):
    directory = os.path.join(os.path.dirname(__file__), '../../jsons')
    os.makedirs(directory, exist_ok=True)

    file_path = os.path.join(directory, 'spotify_playlists.json')
    with open(file_path, 'w') as file:
        json.dump(playlists, file, indent=4)

    print("\nPlaylists saved to jsons/spotify_playlists.json")

if __name__ == '__main__':
    main()
    sys.exit(0)
