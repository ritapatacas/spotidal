import os
import sys
import json
import utils
import spotipy.util as util


def show_tracks(tracks):
    for i, item in enumerate(tracks['items']):
        track = item['track']
        print("   %d %32.32s %s" % (i, track['artists'][0]['name'],
            track['name']))

def get_playlists_names_ids(session):
    playlists_data = session.current_user_playlists()
    print("> Fetching Spotify playlists")
    print(f" > Total spotify playlists: {playlists_data['total']}")
    playlists = [{"id": playlist['id'], "name": playlist['name'], 'sync': 'off' } for playlist in playlists_data['items']]

    #for p in playlists:
    #    print(f"    {p['id']}  {p['name']}")

    return playlists

def get_playlists_details(session):
    username = session.current_user()['id']
    token = util.prompt_for_user_token(username)

    if token:
        playlists = session.user_playlists(username)
        for playlist in playlists['items']:
            if playlist['owner']['id'] == username:
                print()
                print(playlist['name'])
                print ('  total tracks', playlist['tracks']['total'])
                results = session.playlist(playlist['id'],
                    fields="tracks,next")
                tracks = results['tracks']
                show_tracks(tracks)
                while tracks['next']:
                    tracks = session.next(tracks)
                    show_tracks(tracks)
    else:
        print("Can't get token for", username)


def save_playlists_to_json(playlists):
    file = utils.get_file_path('user_data/spotify_playlists.json')

    with open(file, 'w') as file:
        json.dump(playlists, file, indent=4)

    print("\n > Saved to user_data/spotify_playlists.json")


def fetch_and_save_spotify_playlists(session):
    playlists = get_playlists_names_ids(session)
    save_playlists_to_json(playlists)
