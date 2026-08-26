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
                info = playlist.get_info(p)
                if info and info.get("sp_id"):
                    self._sync.by_sp_id(info["sp_id"])
        else:
            info = playlist.get_info(e)
            if info and info.get("sp_id"):
                self._sync.by_sp_id(info["sp_id"])

    def sync_all(self):
        playlists = self.model.get_all_user_playlists()
        total = len(playlists)
        for i, p in enumerate(playlists, start=1):
            print(f"[{i}/{total}] syncing '{p['name']}'")
            self._sync.by_sp_id(p["id"])

    def download(self, e):
        if isinstance(e, list):
            for p in e:
                self.sync(p)
                self._download.by_td_id(playlist.get_info(p)["td_id"])
        else:
            self.sync(e)
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
