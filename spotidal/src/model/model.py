import spotidal.src.model.helpers.utils as utils
from spotidal.src.view.text import Text as t
import spotidal.src.model.helpers.synchronizer as sync
import spotidal.src.model.auth as auth
from spotidal.src.model.helpers.type.file import Files


class Model:
    def __init__(self):
        self.sessions = self.open_sessions()
        self.user_playlists = None
        self.sp_playlist_names = []
        self.current_selection = []
        self.playlist_selection = []
        self.saved_selection = Files.SELECTION.load()
        #self.init()

    def init(self):
        self.get_user_playlists()
        self.get_playlist_names()
        self.get_parsed_playlists()

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
        return utils.fetch_parsed_playlists(sp_playlists, td_playlists)

    def get_current_selection(self):
        return self.current_selection

    def add_to_current_selection(self, e):
        self.current_selection.append(e)

    def get_saved_selection(self):
        saved_selection = Files.SELECTION.load()
        return saved_selection

    def save_selection(self, selected_playlists):
        Files.SELECTION.save(selected_playlists)

    def open_sessions(self):
        sessions = {"sp": auth.open_sp_session(), "td": auth.get_td_session()}
        sp_id = sessions["sp"].me()["id"]
        td_id = sessions["td"].user.id
        try:
            print(t.busy("spotify logged in for " + sp_id))
            print(t.busy("tidal logged in for " + str(td_id)))
        except Exception as e:
            print(t.error("error opening sessions "))
            print(e)
        return sessions

    def get_sessions(self):
        return self.sessions


if __name__ == "__main__":
    model = Model()
