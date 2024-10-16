import sys
from InquirerPy import prompt
from spotidal.src.controller.controller import Controller
from spotidal.src.view.text import Text as t
from spotidal.src.view.prompt import (
    MainMenu,
    SelectionModeMenu,
    SettingsMenu,
    SearchMenu,
    SelectMenu,
    ByIdMenu,
    SaveSelectionMenu
)

app = Controller()
current_selection = []

def main_menu():
    main_menu = MainMenu()
    action = main_menu.display()
    return action

def settings_menu():
    settings_menu = SettingsMenu()
    action = settings_menu.display()
    return action


def selection_mode_menu():
    selection_mode_menu = SelectionModeMenu()
    action = selection_mode_menu.display()
    return action

def search_menu():
    search_menu = SearchMenu()
    result = search_menu.display(app.get_playlist_names())
    current_selection.append(result)
    print(t.display_selection(current_selection))

def save_menu():
    save_menu = SaveSelectionMenu()
    confirm = save_menu.display()
    print('\n\n result confirm ')
    print(confirm)

    if confirm:
        app.save_current_selection(current_selection)
        print(t.log("selection saved"))


def select_menu():
    select_menu = SelectMenu()
    result = select_menu.display(app.get_playlist_names())
    for r in result:
        current_selection.append(r)
    print(t.display_selection(current_selection))

def by_id_menu():
    by_id_menu = ByIdMenu()
    result = by_id_menu.display()
    current_selection.append(app.get_playlist_name(str(result)))
    print(t.display_selection(current_selection))


"""         if confirm("Add more or proceed with selection?"):
            for p in app.get_current_selection():
                action(p)
            app.clear_current_selection()
            break """
def run():
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
                    current_selection = app.load_saved_selection()

                if menu == MainMenu.SYNC[0]:
                    app.sync(current_selection)
                elif menu == MainMenu.DOWNLOAD[0]:
                    app.download(current_selection)

        except KeyboardInterrupt:
            print(t.log("quitting!"))
            sys.exit()


def main():
    print("\n\nSpotidal2u\n")
    run()


if __name__ == "__main__":
    main()
