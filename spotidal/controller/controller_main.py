from spotidal.model import Model
from ..model.helpers.type import PlaylistReference as playlist
import spotidal.view.view as view

from ..model.settings import Settings
from ..model.sync import Sync
from ..model.download import Download
from ..model.flac_to_mp3 import FlacToMp3
from ..model.library import MusicLibrary
from ..model.library_watcher import LibraryWatcher


class ControllerMain:
    def __init__(self, model: Model):
        self.model = model
        self._settings = Settings()
        self._library = MusicLibrary(
            self._settings.get_download_dir(), self._settings.get_database_path()
        )
        self._library.reconcile_all()
        self._library_watcher = None
        if self._settings.get_database_enabled() and self._settings.get_watcher_enabled():
            self._library_watcher = LibraryWatcher(self._library)
            self._library_watcher.start()
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
        FlacToMp3(
            self._settings.get_download_dir(),
            self._settings.get_flac_dir(),
            self._settings.get_mp3_dir(),
            self._settings.get_database_path(),
        ).convert()

    def reconcile_library(self):
        if self._library_watcher:
            self._library_watcher.refresh()

    def stop_library_monitoring(self):
        if self._library_watcher:
            self._library_watcher.stop()

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

    def change_audio_quality(self):
        result = view.audio_quality_menu(
            self._settings.get_download_quality(),
            self._settings.get_quality_fallback(),
        )
        if result.get("target"):
            self._settings.set_download_quality(result["target"])
            self._settings.set_quality_fallback(result.get("fallback", "None"))

    def toggle_mp3_conversion(self):
        settings = self._settings.get_settings()
        value = view.toggle_menu(
            "Automatic MP3 conversion", settings.get("autoConvertMp3", True)
        )
        if value:
            self._settings.set_option("autoConvertMp3", value == "enable")

    def change_database_option(self, action):
        settings = self._settings.get_settings()
        if action == "database enabled":
            value = view.toggle_menu("Database", settings.get("databaseEnabled", True))
            if value:
                enabled = value == "enable"
                self._settings.set_option("databaseEnabled", enabled)
                if not enabled and self._library_watcher:
                    self._library_watcher.stop()
                    self._library_watcher = None
                elif enabled and not self._library_watcher and self._settings.get_watcher_enabled():
                    self._library_watcher = LibraryWatcher(self._library)
                    self._library_watcher.start()
        elif action == "run watcher (update database)":
            self.reconcile_library()
        elif action == "database location path":
            value = view.path_menu(self._settings.get_database_path(), "Database location")
            if value:
                self._settings.set_option("databaseLocation", value)
        elif action == "flac directory":
            value = view.path_menu(self._settings.get_flac_dir(), "FLAC directory")
            if value:
                self._settings.set_option("flacDirectory", value)
        elif action == "mp3 directory":
            value = view.path_menu(self._settings.get_mp3_dir(), "MP3 directory")
            if value:
                self._settings.set_option("mp3Directory", value)
        elif action == "other locations":
            print("> other locations will be implemented later")

    def reset_settings(self):
        self.reset_sp_session()
        self._settings.reset_settings()
        self._settings.check_tidal_login()


if __name__ == "__main__":
    controller = ControllerMain()
