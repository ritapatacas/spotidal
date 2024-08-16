import os
import sys
import yaml
import spotipy
import spotipy.util as util
import utils
from spotipy.oauth2 import SpotifyOAuth


session_file_path = utils.get_file_path('user_data/spotify_session.yml')

SPOTIFY_SCOPES = 'playlist-read-private,user-library-read'


def get_session() -> spotipy.Spotify:
    try:
        with open(session_file_path, 'r') as session_file:
            credentials = yaml.safe_load(session_file)
            print(" > Spotify Credentials loaded")
    except OSError:
        print(" > Error loading Spotify Credentials")

    credentials_manager = SpotifyOAuth(
        username=credentials['spotify']['username'],
        client_id=credentials['spotify']['id'],
        client_secret=credentials['spotify']['secret'],
        redirect_uri=credentials['spotify']['uri'],
        scope=SPOTIFY_SCOPES,
        )
    try:
        credentials_manager.get_access_token(as_dict=False)
    except spotipy.SpotifyOauthError as e:
        sys.exit(f" > Error opening Spotify session; could not get token for username: {credentials['username']}\n{str(e)}")

    return spotipy.Spotify(auth_manager=credentials_manager)



def get_username():
    try:
        with open(session_file_path, 'r') as session_file:
            credentials = yaml.safe_load(session_file)
    except OSError:
        print(" > Error getting Spotify username")
    return credentials['spotify']['username']
