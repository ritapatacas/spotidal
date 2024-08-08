import os
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import yaml

def get_credentials():
    script_dir = os.path.dirname(__file__)
    config_path = os.path.join(script_dir, '../../config.yml')

    with open(config_path, 'r') as file:
        return yaml.safe_load(file)

SPOTIFY_SCOPES = 'playlist-read-private,user-library-read'

def open_session() -> spotipy.Spotify:
    config = get_credentials()

    print("\nOpening Spotify session\n")

    credentials_manager = SpotifyOAuth(
        client_id=config['spotify']['client_id'],
        client_secret=config['spotify']['client_secret'],
        redirect_uri=config['spotify']['redirect_uri'],
        scope=SPOTIFY_SCOPES,
        username=config['spotify']['username'],
        requests_timeout=2
    )

    try:
        credentials_manager.get_access_token(as_dict=False)
    except spotipy.SpotifyOauthError as e:
        sys.exit(f"Error opening Spotify session; could not get token for username: {username}\n{str(e)}")

    return spotipy.Spotify(auth_manager=credentials_manager)
