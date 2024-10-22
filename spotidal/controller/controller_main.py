from spotidal.model import Model
from ..model.helpers.type import PlaylistReference as playlist
import spotidal.view.view as view

from ..model.settings import Settings
from ..model.sync import Sync
from ..model.download import Download


class ControllerMain:
    def __init__(self, model: Model):
        self.model = model
        self._settings = Settings()
        self._sync = Sync(self.model.sessions)
        self._download = Download(self.model.sessions)

    def sync(self, e):
        if isinstance(e, list):
            for p in e:
                self._sync.by_sp_id(playlist.get_info(p)["sp_id"])
        else:
            print("\n\n controller sync e ")
            print(e)
            print(playlist.get_info(e))
            self._sync.by_sp_id(playlist.get_info(e)["sp_id"])

    def download(self, e):
        # todo get rid of get_parsed_playlists running every time
        self.model.get_parsed_playlists()
        if isinstance(e, list):
            for p in e:
                self._download.by_td_id(playlist.get_info(p)["td_id"])
        else:
            self._download.by_td_id(playlist.get_info(e)["td_id"])

    def reset_sp_session(self):
        sp_credentials = view.setup_menu()
        self.model.setup_credentials(sp_credentials)
        self.model.open_sp_session()
    
    def reset_settings(self):
        self.reset_sp_session()
        self._settings.reset_settings()
        self._settings.check_tidal_login()


if __name__ == "__main__":
    controller = ControllerMain()
