from enum import Enum
from InquirerPy import prompt


class Prompt(Enum):
    LIST = "list"
    SEARCH = "fuzzy"
    CONFIRM = "confirm"

    kb_confirm = {
        "confirm": [{"key": "y"}, {"key": "Y"}, {"key": "1"}],
        "reject": [{"key": "n"}, {"key": "N"}, {"key": "0"}],
    }
    INPUT = "input"
    EXPAND = "expand"


class PromptFactory:
    @staticmethod
    def create(
            prompt_type: Prompt,
            message: str,
            choices: list = None,
            confirm: bool = False,
            keybindings: dict = {}
            ) -> dict:

        if prompt_type == Prompt.CONFIRM and confirm:
            return {
                "type": prompt_type.value[0],
                "message": message,
                "name": prompt_type[0],
                "default": True,
                "keybindings": keybindings,
            }
        elif prompt_type == Prompt.LIST:
            return {
                "type": Prompt.LIST.value,
                "message": message,
                "name": "list",
                "choices": choices,
            }
        elif prompt_type == Prompt.INPUT:
            return {
                "type": Prompt.INPUT.value,
                "name": "input",
                "message": message,
            }
        elif prompt_type == Prompt.SEARCH:
            return {
                "type": Prompt.SEARCH.value,
                "message": message,
                "name": "search",
                "choices": choices or [],
                "max_height": "70%",
            }
        else:
            raise ValueError(f"unknown prompt type: {prompt_type}")


class MenuBase:
    def __init__(self, menu_type: Prompt):
        self.menu_type = menu_type

    def display(
        self, message: str, choices: list = None, confirm: bool = False
    ) -> dict:
        print(PromptFactory.create(self.menu_type, message, choices, confirm))




class MainMenu(MenuBase):
    MAIN_Q = "What do you want to do?"
    MAIN = "main", Prompt.LIST

    SYNC = "sync", Prompt.LIST
    DOWNLOAD = "download", Prompt.LIST
    SETTINGS = "settings", Prompt.LIST
    LOAD = "load selection", Prompt.LIST
    SAVE_SELECTION = "save selection", Prompt.CONFIRM

    MAIN_OPT = [SYNC, DOWNLOAD, LOAD, SAVE_SELECTION, SETTINGS]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = [
            opt[0] for opt in self.MAIN_OPT
        ]

    def display(self):
        questions = [
            {
                "type": "list",
                "name": "action",
                "message": self.MAIN_Q,
                "choices": self.options,
            }
        ]
        response = prompt(questions)
        return response["action"]


class SettingsMenu(MenuBase):
    SETTINGS_Q = "Settings"
    DOWNLOAD_DIR = "change download directory"
    DOWNLOAD_QUALITY = "change download quality"
    RESET_SETTINGS = "reset settings"
    SETTINGS_OPT = [DOWNLOAD_DIR, DOWNLOAD_QUALITY, RESET_SETTINGS]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = self.SETTINGS_OPT

    def display(self):
        questions = [
            {
                "type": "list",
                "name": "action",
                "message": self.SETTINGS_Q,
                "choices": self.options,
            }
        ]
        response = prompt(questions)
        return response["action"]


class DownloadDirMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.INPUT)

    def display(self, current: str = None):
        message = "Download directory"
        if current:
            message += f" (current: {current})"
        questions = [
            {
                "type": "input",
                "name": "download_dir",
                "message": message,
                "default": current or "",
            }
        ]
        response = prompt(questions)
        return response["download_dir"]


class DownloadQualityMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self, qualities: list, current: str = None):
        message = "Download quality"
        if current:
            message += f" (current: {current})"
        questions = [
            {
                "type": "list",
                "name": "quality",
                "message": message,
                "choices": qualities,
            }
        ]
        response = prompt(questions)
        return response["quality"]


class SaveSelectionMenu(MenuBase):
    SAVE_SELECTION_Q = "Save selection?"
    SAVE_SELECTION = "save selection", Prompt.CONFIRM

    def __init__(self):
        super().__init__(Prompt.CONFIRM)

    def display(self):
        questions = [
            {
                "type": "confirm",
                "name": "save_selection",
                "message": self.SAVE_SELECTION_Q,
                "default": True,
                "keybindings": {
                    "confirm": [{"key": "y"}, {"key": "Y"}, {"key": "1"}],
                    "reject": [{"key": "n"}, {"key": "N"}, {"key": "0"}],
                },
            }
        ]
        response = prompt(questions)
        return response["save_selection"]


class SelectionModeMenu(MenuBase):
    SELECTION_Q = "Which playlists?"
    SEARCH = "search", Prompt.SEARCH
    SELECT = "select", Prompt.LIST
    BY_ID = "by_id", Prompt.INPUT
    LOAD = "load saved selection"
    SELECTION_OPT = [SEARCH, SELECT, BY_ID, LOAD]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = [
            opt[0] for opt in self.SELECTION_OPT
        ]

    def display(self):
        questions = [
            {
                "type": "list",
                "name": "action",
                "message": self.SELECTION_Q,
                "choices": self.options,
            }
        ]
        response = prompt(questions)
        return response["action"]


class SelectMenu(MenuBase):
    SELECT_Q = "Select playlists (all = a, none = n)"
    SELECT_ERR = "Select at least one playlist"

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.playlists = None

    def display(self, playlists: list):
        keybindings_select_list = {
            "toggle-all-true": [{"key": "a"}],
            "toggle-all-false": [{"key": "n"}],
        }
        questions = [
            {
                "type": "checkbox",
                "message": self.SELECT_Q,
                "name": "selected_playlists",
                "choices": playlists,
            }
        ]
        response = prompt(questions, keybindings=keybindings_select_list)
        if not response["selected_playlists"]:
            print(self.SELECT_ERR)
        return response["selected_playlists"]


class SearchMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.SEARCH)
        self.playlists = None

    def display(self, playlists: list):
        questions = [
            {
                "type": "fuzzy",
                "message": "Search",
                "name": "search_playlists",
                "choices": playlists,
                "max_height": "70%",
            }
        ]
        response = prompt(questions)
        return response["search_playlists"]


class ByIdMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.INPUT)

    def display(self):
        questions = [
            {
                "type": "input",
                "name": "playlist_id",
                "message": "Tell me a spotify playlist id",
            }
        ]
        response = prompt(questions)
        return response["playlist_id"]


class ConfirmMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.CONFIRM)

    def display(self, message: str):
        questions = [
            {
                "type": "confirm",
                "name": "confirm",
                "message": message,
                "default": True,
                "keybindings": {
                    "confirm": [
                        {"key": "y"},
                        {"key": "Y"},
                        {"key": "p"},
                        {"key": "P"},
                        {"key": "1"},
                    ],
                    "reject": [
                        {"key": "n"},
                        {"key": "N"},
                        {"key": "a"},
                        {"key": "A"},
                        {"key": "0"},
                    ],
                },
            }
        ]
        response = prompt(questions)
        return response["confirm"]


ID_Q = "Spotify playlist ID to sync"
ID_ERR = "invalid Spotify playlist ID"

ADD_MORE_Q = "Add more or can we proceed?"
SAVE_SELECTION_Q = "Save selection?"
RESET_Q = "Are you sure reset settings?"

SAVED_LOG = "saved"
LOADED_LOG = "loaded"
QUIT_LOG = "quitting!"
MAIN = "main", Prompt.LIST
SYNC = "sync", Prompt.LIST
DOWNLOAD = "download", Prompt.LIST
LOAD = "load saved selection"
SAVE = "save selection", Prompt.CONFIRM
SETTINGS = "settings", Prompt.LIST
MAIN_OPT = [SYNC, DOWNLOAD, LOAD, SAVE, SETTINGS]

SEARCH = "search", Prompt.SEARCH
SELECT = "select", Prompt.LIST
BY_ID = "by_id", Prompt.INPUT
SELECTION_OPT = [SEARCH, SELECT, BY_ID, LOAD]

RESET_SETTINGS = "reset settings"
SETTINGS_OPT = [RESET_SETTINGS]
