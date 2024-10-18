import spotidal.model.auth as auth
from ..model.helpers import synchronizer as sync
from ..model.helpers.utils import fetch_parsed_playlists
from ..model.helpers.type.file import Files
from ..view.text import Text as t


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
        
    def get_user_playlists(self):
        self.user_playlists = self.sessions["sp"].current_user_playlists()["items"]
        return self.user_playlists

    def get_playlist_names(self):
        self.user_playlists = self.sessions["sp"].current_user_playlists()["items"]
        names = []
        for p in self.user_playlists:
            names.append(p["name"])
        self.sp_playlist_names = names
        return names

    def get_parsed_playlists(self):
        sp_playlists = self.sessions["sp"].current_user_playlists()["items"]
        td_playlists = sync._playlists.get_td_playlists(self.sessions["td"])
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

if __name__ == "__main__":
    model = Model()
