from pickletools import read_long1
import re
import sys
import spotipy as sp_api
import tidalapi as td_api
import webbrowser
from .helpers.type.file import Files
from ..view.text import Text as t
from ..view.setup import get_credentials

__all__ = ["open_sp_session", "open_td_session"]

SPOTIFY_SCOPES = "playlist-read-private, user-library-read"
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"


def open_sp_session() -> sp_api.Spotify:
    try:
        credentials = (Files.CREDENTIALS.load() or {}).get("spotify")
        if not credentials:
            raise KeyError("spotify")
    except:
        t.error("no spotify credentials found, please provide them")
        return False

    auth = sp_api.SpotifyOAuth(
        username=credentials["username"],
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"],
        scope=SPOTIFY_SCOPES,
        redirect_uri=credentials.get("redirect_uri", SPOTIFY_REDIRECT_URI),
        requests_timeout=2,
    )

    
    try:
        auth.get_access_token(as_dict=False)
    except sp_api.SpotifyOauthError:
        sys.exit(t.error("error opening spotify session > could not get token"))
    save_sp_credentials(credentials)
    return sp_api.Spotify(oauth_manager=auth)


def open_td_session() -> td_api.Session:
    session = td_api.Session()
    login, future = session.login_oauth()
    print(t.log(f"login with the webbrowser '{login.verification_uri_complete}'"))

    url = login.verification_uri_complete
    if not url.startswith("https://"):
        url = "https://" + url
    webbrowser.open(url)
    future.result()
    sp_credentials = None
    
    try:
        sp_credentials = Files.CREDENTIALS.load()["spotify"]
    except:
        t.error("no spotify credentials found")

    Files.CREDENTIALS.save(
        {
            "spotify": sp_credentials,
            "tidal": {
                "session_id": session.session_id,
                "token_type": session.token_type,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
            },
        }
    )

    return session


def save_sp_credentials(credentials: dict):
    td = {}
    try:
        td = Files.CREDENTIALS.load()["tidal"]
    except:
        td = {}
        
    Files.CREDENTIALS.save(
        {
            "spotify": {
                "username": credentials["username"],
                "client_id": credentials["client_id"],
                "client_secret": credentials["client_secret"],
                "scope": SPOTIFY_SCOPES,
                "redirect_uri": credentials.get("redirect_uri", SPOTIFY_REDIRECT_URI),
                "requests_timeout": 2,
            },
            "tidal": td,
        }
    )
    pass
    credentials = {
        "username": credentials["username"],
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
        "scope": SPOTIFY_SCOPES,
        "redirect_uri": credentials.get("redirect_uri", SPOTIFY_REDIRECT_URI),
        "requests_timeout": 2,
    }

def save_td_session(session: td_api.Session):
    Files.CREDENTIALS.save(
        {
            "spotify": Files.CREDENTIALS.load()["spotify"],
            "tidal": {
                "session_id": session.session_id,
                "token_type": session.token_type,
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
            },
        }
    )


def get_td_session() -> td_api.Session:
    previous_session = None
    try:
        previous_session = Files.CREDENTIALS.load()["tidal"]
    except:
        t.error("no tidal session found, opening new session")
        
    session = td_api.Session()
    if previous_session:
        try:
            if session.load_oauth_session(
                token_type=previous_session["token_type"],
                access_token=previous_session["access_token"],
                refresh_token=previous_session["refresh_token"],
            ):
                return session
        except Exception as e:
            print(t.error("error loading previous tidal session \n" + str(e)))
    else:
        print(t.error("no previous tidal session found"))
    print(t.log("opening new tidal session"))
    return open_td_session()


def open_sessions():
    try:
        sp = open_sp_session()
    except:
        print(t.error(f"error opening spotify session"))
        return False
    try:
        td = get_td_session()
    except Exception as e:
        print(t.error(f"error opening tidal session: {str(e)}"))
        td = open_td_session()

    return sp, td
