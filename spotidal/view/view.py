import re
import sys
from InquirerPy import prompt

from spotidal.view.setup import get_credentials
from spotidal.view.text import Text as t
from spotidal.view.prompt import (
    MainMenu,
    SelectionModeMenu,
    SettingsMenu,
    DownloadDirMenu,
    DownloadQualityMenu,
    SearchMenu,
    SelectMenu,
    SaveSelectionMenu,
    ConfirmMenu,
    URLMenu,
)

#app = Controller()
current_selection = set()

def setup_menu():
    sp_credentials = get_credentials()
    return sp_credentials


def get_remaining_playlists():
    playlists = set(app.get_playlist_names())
    remaining_playlists = playlists - current_selection 
    return list(remaining_playlists)

def clear_selection():
    global current_selection
    current_selection = set()

def main_menu():
    main_menu = MainMenu()
    print('')
    action = main_menu.display()
    return action

def settings_menu():
    settings_menu = SettingsMenu()
    action = settings_menu.display()
    return action

def download_dir_menu(current=None):
    return DownloadDirMenu().display(current)

def download_quality_menu(qualities, current=None):
    return DownloadQualityMenu().display(qualities, current)

def confirm_selection_menu():
    confirm_menu = ConfirmMenu()
    response = confirm_menu.display(
        "Proceed with selection or add more playlists? (y to proceed, n to add more)"
    )
    return response

def selection_mode_menu(include_url=False):
    selection_mode_menu = SelectionModeMenu()
    action = selection_mode_menu.display(include_url)
    return action

def search_menu(get_remaining_playlists):
    while True:
        search_menu = SearchMenu()
        result = search_menu.display(get_remaining_playlists)
        return result

def save_menu():
    save_menu = SaveSelectionMenu()
    confirm = save_menu.display()
    if confirm:
        return current_selection

def select_menu(get_remaining_playlists):
    select_menu = SelectMenu()
    result = select_menu.display(get_remaining_playlists)
    print('view select menu result')
    print(result)
    return result

def url_menu():
    return URLMenu().display()

""" def run():
    global current_selection
    
    while True:
        if len(current_selection) > 0:
            print(t.display_selection(current_selection))

        menu = main_menu()

        try:
            if menu == MainMenu.SETTINGS[0]:
                action = settings_menu()
                if action == SettingsMenu.RESET_SETTINGS[0]:
                    app.reset_settings()

            elif menu == MainMenu.LOAD[0]:
                current_selection = set(app.load_saved_selection())

            elif menu == MainMenu.SAVE_SELECTION[0]:
                save_menu()

            elif menu == MainMenu.SYNC[0] or menu == MainMenu.DOWNLOAD[0]:
                action = selection_mode_menu()

                if action == SelectionModeMenu.SEARCH[0]:
                    search_menu()

                elif action == SelectionModeMenu.SELECT[0]:
                    select_menu()

                elif action == SelectionModeMenu.BY_ID[0]:
                    by_id_menu()

                elif action == SelectionModeMenu.LOAD[0]:
                    current_selection = set(app.load_saved_selection())

                if menu == MainMenu.SYNC[0]:
                    app.sync(list(current_selection))
                elif menu == MainMenu.DOWNLOAD[0]:
                    app.download(list(current_selection))
                    clear_selection()

        except KeyboardInterrupt:
            print(t.log("quitting!"))
            sys.exit() """

def main():
    print("\nSpotidal2u")
    setup_menu()
    #run()

if __name__ == "__main__":
    main()
