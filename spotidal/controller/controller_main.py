from spotidal.model import Model
from ..model.helpers.type import PlaylistReference as playlist
import spotidal.view.view as view

from ..model.settings import Settings
from ..model.sync import Sync
from ..model.download import Download
from ..model.flac_to_mp3 import FlacToMp3


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

    def download(self, e):
        if isinstance(e, list):
            for p in e:
                self.sync(p)
                self._download.by_td_id(playlist.get_info(p)["td_id"])
        else:
            self.sync(e)
            self._download.by_td_id(playlist.get_info(e)["td_id"])

    def download_url(self, url):
        self._download.by_url(url)

    def get_download_dir(self):
        return self._settings.get_download_dir()

    def flac_to_mp3(self):
        FlacToMp3(self._settings.get_download_dir()).convert()

    def reset_sp_session(self):
        sp_credentials = view.setup_menu()
        self.model.setup_credentials(sp_credentials)
        self.model.open_sp_session()
    
    def change_download_dir(self):
        new_dir = view.download_dir_menu(self._settings.get_download_dir())
        if new_dir:
            saved = self._settings.set_download_dir(new_dir)
            print(f"> download directory set to {saved}")

    def change_download_quality(self):
        from ..model.settings import QUALITY_OPTIONS

        quality = view.download_quality_menu(
            QUALITY_OPTIONS, self._settings.get_download_quality()
        )
        if quality:
            self._settings.set_download_quality(quality)
            print(f"> download quality set to {quality}")

    def reset_settings(self):
        self.reset_sp_session()
        self._settings.reset_settings()
        self._settings.check_tidal_login()


if __name__ == "__main__":
    controller = ControllerMain()
