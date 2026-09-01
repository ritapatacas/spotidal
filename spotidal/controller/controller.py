import sys
from spotidal.model.model import Model
from spotidal.controller.playlist_controller import PlaylistController
from spotidal.controller.controller_main import ControllerMain

import spotidal.view.view as view
from spotidal.view.text import Text as t
from spotidal.model.helpers.td_downloader import (
    TidalSessionStaleError,
    pop_conversion_messages,
)
from spotidal.view.setup import get_credentials

from spotidal.view.prompt import (
    MainMenu,
    SelectionModeMenu,
    SettingsMenu,
    UtilsMenu,
)


class Controller:
    def __init__(self):
        self.model = Model()
        self.init_sessions()
        self.app = ControllerMain(self.model)
        print(t.busy(f"download dir: {self.app.get_download_dir()}"))
        for warning in self.app.get_startup_warnings():
            print(t.warning(warning))
        self.playlists = PlaylistController(self.model)




    def init_sessions(self):
        sp = self.model.open_sp_session()
        if not sp:
            self.model.setup_credentials(get_credentials())
            sp = self.model.open_sp_session()
        try:
            td = self.model.open_td_session()
        except Exception as e:
            sys.exit(t.error(f"unable to authenticate with TIDAL: {e}"))
        if not td:
            sys.exit(t.error("unable to authenticate with TIDAL; please try again"))
        self.model.sessions = {"sp": sp, "td": td}

        log = self.model.get_session_log()
        for account in log.splitlines():
            print(t.busy(account))

    def run(self):
        while True:
            try:
                for message in pop_conversion_messages():
                    print(message)
                menu = view.main_menu()
                if menu == MainMenu.QUIT[0]:
                    self.app.stop_library_monitoring()
                    print(t.log("quitting!"))
                    sys.exit()
                elif menu == MainMenu.SETTINGS[0]:
                    action = view.settings_menu()
                    if action == SettingsMenu.DOWNLOAD_SETTINGS:
                        self._download_settings()
                    elif action == SettingsMenu.DATABASE_SETTINGS:
                        self._database_settings()
                    elif action == SettingsMenu.HELP:
                        print(t.log(
                            "spotidal — sync and download playlists from Spotify via TIDAL.\n"
                            "  download: pick playlists and download them\n"
                            "  sync: pick playlists and keep them in sync\n"
                            "  convert: convert downloaded FLAC files to MP3\n"
                            "  utils: playlist selection, tmp cleanup, session refresh, database tools\n"
                            "  settings: downloads and database configuration"
                        ))

                elif menu == MainMenu.UTILS[0]:
                    self._utils_menu()

                elif menu == MainMenu.SYNC[0] or menu == MainMenu.DOWNLOAD[0]:
                    if self.model.current_selection:
                        print(t.display_selection(self.model.current_selection))
                    action = view.selection_mode_menu(True)

                    if action == SelectionModeMenu.SEARCH[0]:
                        playlists = (
                            self.playlists.names()
                            if menu == MainMenu.DOWNLOAD[0]
                            else self.playlists.not_selected()
                        )
                        selected = view.search_menu(playlists)
                        if not selected:
                            continue
                        self.model.current_selection.add(selected)

                    elif action == SelectionModeMenu.SELECT[0]:
                        result = view.select_menu(self.playlists.not_selected())
                        if not result:
                            continue
                        for r in result:
                            self.model.current_selection.add(r)

                    elif action == SelectionModeMenu.LOAD:
                        selection = set(self.playlists.load())
                        if menu == MainMenu.DOWNLOAD[0]:
                            filtered = self.app.filter_playlists_with_missing(selection)
                            skipped = len(selection) - len(filtered)
                            if skipped:
                                print(t.log(
                                    f"skipped {skipped} playlist(s) already fully downloaded"
                                ))
                            selection = filtered
                        self.model.current_selection = selection

                    elif action == SelectionModeMenu.URL:
                        url = view.url_menu()
                        if url:
                            try:
                                if menu == MainMenu.DOWNLOAD[0]:
                                    self.app.download_url(url)
                                else:
                                    self.app.sync_url(url)
                            except ValueError as error:
                                print(t.error(str(error)))
                        continue

                    elif action == SelectionModeMenu.BACK[0]:
                        continue

                    if not action:
                        continue
                    if menu == MainMenu.SYNC[0]:
                        self.app.sync(list(self.model.current_selection))
                    elif menu == MainMenu.DOWNLOAD[0]:
                        self.app.download(list(self.model.current_selection))
                        self.model.current_selection = set()

                elif menu == MainMenu.CONVERT[0]:
                    self.app.flac_to_mp3()

            except KeyboardInterrupt:
                self.app.stop_library_monitoring()
                print(t.log("quitting!"))
                sys.exit()
            except TidalSessionStaleError:
                print(t.error(
                    "TIDAL session is stale; refreshing access token before continuing"
                ))
                if self.app.refresh_td_session():
                    print(t.log("TIDAL access token refreshed"))
                else:
                    print(t.warning("unable to refresh TIDAL access token"))
            except Exception as error:
                print(t.error(f"error: {error}"))

    def _download_settings(self):
        while True:
            action = view.download_settings_menu()
            if action in (None, "back"):
                return
            if action == "download directory":
                self.app.change_download_dir()
            elif action == "audio quality":
                self.app.change_audio_quality()
            elif action == "automatic mp3 conversion":
                self.app.toggle_mp3_conversion()
            elif action == "tidekeeper additional settings":
                self._tidekeeper_settings()

    def _default_selection(self):
        while True:
            action = view.default_selection_menu()
            if action in (None, "back"):
                return
            if action == "view selection":
                selection = self.playlists.load()
                if not selection:
                    print("> no default playlists selected")
                else:
                    stats = self.app.get_selection_stats(selection)
                    print(t.display_selection_table(stats))
            elif action == "refresh selection stats":
                selection = self.playlists.load()
                if not selection:
                    print("> no default playlists selected")
                else:
                    stats = self.app.get_selection_stats(selection, force_refresh=True)
                    print(t.display_selection_table(stats))
            elif action == "change selection":
                selection = view.select_menu(
                    self.playlists.names(), self.playlists.load()
                )
                if selection:
                    self.playlists.save(selection)
                    print(t.log("default playlist selection saved"))

    def _watch_playlist_files(self):
        selection = set()
        while True:
            if selection:
                print(t.display_selection(selection))
            action = view.selection_mode_menu(True)
            if action in (None, SelectionModeMenu.BACK[0]):
                return
            if action == SelectionModeMenu.SEARCH[0]:
                selected = view.search_menu(self.playlists.not_selected())
                if selected:
                    selection.add(selected)
            elif action == SelectionModeMenu.SELECT[0]:
                result = view.select_menu(self.playlists.not_selected())
                if result:
                    for r in result:
                        selection.add(r)
            elif action == SelectionModeMenu.LOAD:
                selection |= set(self.playlists.load())
            elif action == SelectionModeMenu.URL:
                url = view.url_menu()
                if url:
                    try:
                        name = self.app.resolve_playlist_name_from_url(url)
                        selection.add(name)
                    except ValueError as error:
                        print(t.error(str(error)))
            if not selection:
                continue
            if view.confirm_selection_menu():
                break
        stats = self.app.get_selection_stats(selection, force_refresh=True)
        print(t.display_selection_table(stats))

    def _utils_menu(self):
        while True:
            action = view.utils_menu()
            if action in (None, "back"):
                return
            if action == UtilsMenu.MANAGE_SELECTED_PLAYLIST:
                self._default_selection()
            elif action == UtilsMenu.CLEAN_TMP:
                self.app.clean_tmp()
            elif action == UtilsMenu.REFRESH_SESSION:
                if self.app.refresh_td_session():
                    print(t.log("TIDAL access token refreshed"))
                else:
                    print(t.warning("unable to refresh TIDAL access token"))
            elif action == UtilsMenu.TIDEKEEPER_DOCTOR:
                self.app.tidekeeper_doctor()
            elif action == UtilsMenu.RUN_WATCHER:
                self.app.reconcile_library()
            elif action == UtilsMenu.WATCH_PLAYLIST_FILES:
                self._watch_playlist_files()
            elif action == UtilsMenu.CONVERT_TO_FLAC:
                self.app.normalize_to_flac()
            elif action == UtilsMenu.FIX_MISSING_DATA:
                self.app.fill_missing_database_data()

    def _database_settings(self):
        while True:
            action = view.database_settings_menu()
            if action in (None, "back"):
                return
            self.app.change_database_option(action)

    def _tidekeeper_settings(self):
        while True:
            action = view.tidekeeper_settings_menu()
            if action in (None, "back"):
                return
            print(t.log(f"Tidekeeper setting '{action}' will be implemented later"))

def main():
    print(f"\n{t.red('Spotidal')}\n")
    controller = Controller()
    controller.run()


if __name__ == "__main__":
    main()
