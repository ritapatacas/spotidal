from enum import Enum
from InquirerPy import prompt


BACK_KEYBINDINGS = {"skip": [{"key": "escape"}]}


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
    FLAC_TO_MP3 = "flac to mp3", Prompt.LIST
    SETTINGS = "settings", Prompt.LIST

    MAIN_OPT = [DOWNLOAD, SYNC, SETTINGS, FLAC_TO_MP3]

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
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("action")


class SettingsMenu(MenuBase):
    SETTINGS_Q = "Settings"
    DOWNLOAD_DIR = "change download directory"
    DOWNLOAD_QUALITY = "change download quality"
    RESET_SETTINGS = "reset settings"
    LOAD = "load selection"
    SAVE_SELECTION = "save selection"
    BACK = "back"
    SETTINGS_OPT = [DOWNLOAD_DIR, DOWNLOAD_QUALITY, RESET_SETTINGS, LOAD, SAVE_SELECTION, BACK]

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
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("action")


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
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("download_dir")


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
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("quality")


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
                "mandatory": False,
                "keybindings": {
                    **BACK_KEYBINDINGS,
                    "confirm": [{"key": "y"}, {"key": "Y"}, {"key": "1"}],
                    "reject": [{"key": "n"}, {"key": "N"}, {"key": "0"}],
                },
            }
        ]
        response = prompt(questions)
        return response.get("save_selection")


class SelectionModeMenu(MenuBase):
    SELECTION_Q = "How do you want to proceed?"
    SEARCH = "search", Prompt.SEARCH
    SELECT = "selected", Prompt.LIST
    BACK = "back", Prompt.LIST
    URL = "url"
    SELECTION_OPT = [SEARCH, SELECT, BACK]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = [
            opt[0] for opt in self.SELECTION_OPT
        ]

    def display(self, include_url=False):
        options = ([self.URL] if include_url else []) + self.options
        questions = [
            {
                "type": "list",
                "name": "action",
                "message": self.SELECTION_Q,
                "choices": options,
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("action")


class URLMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.INPUT)

    def display(self):
        questions = [
            {
                "type": "input",
                "name": "url",
                "message": "TIDAL or Spotify URL",
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("url")


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
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions, keybindings=keybindings_select_list)
        if not response.get("selected_playlists"):
            print(self.SELECT_ERR)
        return response.get("selected_playlists")


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
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("search_playlists")


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
                "mandatory": False,
                "keybindings": {
                    **BACK_KEYBINDINGS,
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
        return response.get("confirm")
