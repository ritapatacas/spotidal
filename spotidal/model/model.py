import spotidal.model.auth as auth
from ..model.helpers.sync.playlists_handler import get_td_playlists
from ..model.helpers.utils import fetch_parsed_playlists
from ..model.helpers.type.file import Files
from ..view.text import Text as t
from .helpers.td_downloader import login_tidekeeper, refresh_tidekeeper_token


class Model:
    def __init__(self):
        self.sessions = None
        self.user_playlists = None
        self.sp_playlist_names = None
        self.current_selection = set()
        self.remaining_playlists = set()
        self.saved_selection = []

    def setup_credentials(self, credentials):
        auth.save_sp_credentials(credentials)
    
    def get_session_log(self):
        sp_id = self.sessions["sp"].me()["id"]
        td_id = self.sessions["td"].user.id

        return "spotify user " + sp_id + "\ntidal user " + str(td_id)
        
    def get_user_playlists(self):
        self.user_playlists = self.sessions["sp"].current_user_playlists()["items"]
        return self.user_playlists

    def get_playlist_names(self):
        response = self.sessions["sp"].current_user_playlists(limit=50)
        playlists = response["items"]
        while response.get("next"):
            response = self.sessions["sp"].next(response)
            playlists.extend(response["items"])

        self.user_playlists = playlists
        names = []
        for p in self.user_playlists:
            names.append(p["name"])
        self.sp_playlist_names = names
        return names

    def get_parsed_playlists(self):
        sp_playlists = self.sessions["sp"].current_user_playlists()["items"]
        td_playlists = get_td_playlists(self.sessions["td"])
        return fetch_parsed_playlists(sp_playlists, td_playlists)

    def add_to_current_selection(self, e):
        self.current_selection.add(e)

    def get_saved_selection(self):
        saved_selection = Files.SELECTION.load()
        return set(saved_selection)

    def save_selection(self, selected_playlists):
        Files.SELECTION.save(list(selected_playlists))  
    
    
    def open_sp_session(self):
        sp = auth.open_sp_session()
        if not sp:
            return False
        return sp
    
    def open_td_session(self):
        td = auth.get_td_session()
        if not td:
            return False
        return td

    def refresh_td_session(self):
        session = self.sessions["td"]
        try:
            credentials = refresh_tidekeeper_token()
            if credentials:
                session.access_token = credentials["access_token"]
                session.refresh_token = credentials["refresh_token"]
                auth.save_td_session(session)
                return True
            if session.refresh_token:
                refreshed = session.token_refresh(session.refresh_token)
                if refreshed:
                    auth.save_td_session(session)
                    return True
        except Exception as error:
            print(t.error(
                f"TIDAL session refresh failed ({type(error).__name__}): {error}"
            ))

        print(t.warning("TIDAL refresh token rejected; opening a tidekeeper login"))
        try:
            credentials = login_tidekeeper()
        except Exception as error:
            print(t.error(
                f"TIDAL login failed ({type(error).__name__}): {error}"
            ))
            return False
        session.access_token = credentials["access_token"]
        session.refresh_token = credentials["refresh_token"]
        auth.save_td_session(session)
        return True

if __name__ == "__main__":
    model = Model()
