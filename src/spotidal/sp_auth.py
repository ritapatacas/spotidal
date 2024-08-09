import os
import sys
import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

def get_credentials():
    load_dotenv()
    credentials = {
        'username': os.getenv('SPOTIFY_CLIENT_USERNAME'),
        'client_id': os.getenv('SPOTIFY_CLIENT_ID'),
        'client_secret': os.getenv('SPOTIFY_CLIENT_SECRET'),
        'redirect_uri': os.getenv('SPOTIFY_REDIRECT_URI'),
    }
    return credentials

SPOTIFY_SCOPES = 'playlist-read-private,user-library-read'

def open_session() -> spotipy.Spotify:
    credentials = get_credentials()

    print("\nOpening Spotify session\n")

    credentials_manager = SpotifyOAuth(
        client_id=credentials['client_id'],
        client_secret=credentials['client_secret'],
        redirect_uri=credentials['redirect_uri'],
        scope=SPOTIFY_SCOPES,
        username=credentials['username'],
        requests_timeout=2
    )

    try:
        credentials_manager.get_access_token(as_dict=False)
    except spotipy.SpotifyOauthError as e:
        sys.exit(f"Error opening Spotify session; could not get token for username: {credentials['username']}\n{str(e)}")

    return spotipy.Spotify(auth_manager=credentials_manager)


def get_token():
    credentials = get_credentials()
    username = credentials['username']
    scope = 'user-library-read'

    token = util.prompt_for_user_token(username, scope)

    if token:
        print("Token successfully retrieved!", token)
    else:
        print("Failed to retrieve token.")

""" if __name__ == '__main__':
    get_token()
 """
