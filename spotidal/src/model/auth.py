import sys
import spotipy as sp_api
import tidalapi as td_api
import webbrowser
import spotidal.src.model.helpers.utils as utils
from spotidal.src.model.helpers.type.file import Files
from spotidal.src.view.text import Text as t


__all__ = ["open_sp_session", "open_td_session"]

SPOTIFY_SCOPES = "playlist-read-private, user-library-read"


def open_sp_session() -> sp_api.Spotify:
    credentials = Files.SP_SESSION.load()["spotify"]
    scope = "user-library-read playlist-read-private user-follow-read playlist-modify-private playlist-modify-public"

    auth = sp_api.SpotifyOAuth(
        username=credentials["username"],
        scope=scope,
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"],
        redirect_uri=credentials["redirect_uri"],
        requests_timeout=2,
    )
    try:
        auth.get_access_token(as_dict=False)
    except sp_api.SpotifyOauthError:
        sys.exit(t.error("error opening spotify session > could not get token"))
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
    Files.TD_SESSION.save(
        {
            "session_id": session.session_id,
            "token_type": session.token_type,
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
        }
    )

    return session

def get_td_session() -> td_api.Session:
    previous_session = Files.TD_SESSION.load()

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
        print(t.error("no previous tidal session found, opening new session"))
        open_td_session()
