import sys
from spotidal.model.model import Model
from spotidal.controller.playlist_controller import PlaylistController
from spotidal.controller.controller_main import ControllerMain

import spotidal.view.view as view
from spotidal.view.text import Text as t
from spotidal.view.setup import get_credentials

from spotidal.view.prompt import (
    MainMenu,
    SelectionModeMenu,
    SettingsMenu,
)


class Controller:
    def __init__(self):
        self.model = Model()
        self.init_sessions()
        self.app = ControllerMain(self.model)
        self.playlists = PlaylistController(self.model)




    def init_sessions(self):
        sp = self.model.open_sp_session()
        if not sp:
            self.model.setup_credentials(get_credentials())
            sp = self.model.open_sp_session()
        td = self.model.open_td_session()
        self.model.sessions = {"sp": sp, "td": td}
        self.model.get_parsed_playlists()
        
        log = self.model.get_session_log()
        print(t.log_grey(log))

    def run(self):
        while True:
            try:
                menu = view.main_menu()
                if menu == MainMenu.SETTINGS[0]:
                    action = view.settings_menu()
                    if action == SettingsMenu.DOWNLOAD_DIR:
                        self.app.change_download_dir()
                    elif action == SettingsMenu.DOWNLOAD_QUALITY:
                        self.app.change_download_quality()
                    elif action == SettingsMenu.RESET_SETTINGS:
                        self.app.reset_settings()
                    
                elif menu == MainMenu.LOAD[0]:
                    self.model.current_selection = self.playlists.load()
                
                elif menu == MainMenu.SAVE_SELECTION[0]:
                    self.playlists.save(view.save_menu())
                
                elif menu == MainMenu.SYNC[0] or menu == MainMenu.DOWNLOAD[0]:
                    action = view.selection_mode_menu()

                    if action == SelectionModeMenu.SEARCH[0]:
                        selected = view.search_menu(self.playlists.not_selected())
                        if selected:
                            self.model.current_selection.add(selected)

                    elif action == SelectionModeMenu.SELECT[0]:
                        result = view.select_menu(self.playlists.not_selected())
                        for r in result:
                            self.model.current_selection.add(r)

                    elif action == SelectionModeMenu.BY_ID[0]:
                        selected = view.by_id_menu()
                        if selected:
                            self.model.current_selection.add(selected)

                    elif action == SelectionModeMenu.LOAD[0]:
                        self.model.current_selection = set(self.playlists.load())

                    if menu == MainMenu.SYNC[0]:
                        self.app.sync(list(self.model.current_selection))
                    elif menu == MainMenu.DOWNLOAD[0]:
                        self.app.download(list(self.model.current_selection))
                        self.model.current_selection = set()
                        
            except KeyboardInterrupt:
                print(t.log("quitting!"))
                sys.exit()

def main():
    print("\nSpotidal2u")
    controller = Controller()
    controller.run()


if __name__ == "__main__":
    main()
