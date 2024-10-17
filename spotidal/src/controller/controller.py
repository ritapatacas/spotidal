from ..model import Model
from ..model.helpers.type import PlaylistReference as playlist

from ..model.settings import Settings
from ..model.sync import Sync
from ..model.download import Download

class Controller:
    def __init__(self):
        self._model = Model()
        self.sessions = self._model.sessions
        self._settings = Settings()
        self._sync = Sync(self.sessions)
        self._download = Download(self.sessions)

    def get_playlist_name(self, ref):
        print(playlist.get_info(ref))
        return playlist.get_info(ref)["name"]

    def get_playlist_names(self):
        return self._model.get_playlist_names()

    def load_saved_selection(self):
        return self._model.get_saved_selection()


    def save_current_selection(self, selected_playlists):
        self._model.save_selection(selected_playlists)


    def get_current_selection(self):
        return self._model.get_current_selection()

    def add_to_current_selection(self, e):
        self.current_selection.add(e)

    def get_saved_selection(self):
        return self.get_saved_selection()


    def sync(self, e):
        if isinstance(e, list):
            for p in e:
                self._sync.by_sp_id(playlist.get_info(p)["sp_id"])
        else:
            print('\n\n controller sync e ')
            print(e)
            print(playlist.get_info(e))
            self._sync.by_sp_id(playlist.get_info(e)["sp_id"])

    def download(self, e, sync=True):
        if isinstance(e, list):
            for p in e:
                self._download.by_td_id(playlist.get_info(p)["td_id"])
        else:
            self._download.by_td_id(playlist.get_info(e)["td_id"])

    def reset_settings(self):
        self._settings.reset_settings()
        self._settings.check_tidal_login()


if __name__ == "__main__":
    controller = Controller()
