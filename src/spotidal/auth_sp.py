import os
import yaml
import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyOAuth


project_root = os.path.abspath(os.path.join(
os.path.dirname(__file__), '..', '..'))
os.makedirs(project_root, exist_ok=True)
session_file_path = os.path.join(project_root, 'spotify_session.yml')
SPOTIFY_SCOPES = 'playlist-read-private,user-library-read'


def get_session() -> spotipy.Spotify:
    try:
        with open(session_file_path, 'r') as session_file:
            credentials = yaml.safe_load(session_file)
            print("Spotify Credentials loaded\n")
    except OSError:
        print("Error loading Spotify Credentials")

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
        sys.exit(f"Error opening Spotify session; could not get token for username: {credentials['username']}\n{str(e)}")

    return spotipy.Spotify(auth_manager=credentials_manager)



""" def get_tidal_client():
    return tidalapi.Session()

session = get_tidal_client()
print(session)

login, future = session.login_oauth()

notification.notify("Open the URL to log in", login.verification_uri_complete)

def get_token():
    credentials = get_credentials()
    username = credentials['username']
    scope = 'user-library-read'

    token = util.prompt_for_user_token(username, scope)

    if token:
        print("Token successfully retrieved!", token)
    else:
        print("Failed to retrieve token.")

 """
