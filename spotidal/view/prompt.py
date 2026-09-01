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
    MAIN_Q = "what do you want to do?"
    MAIN = "main", Prompt.LIST

    SYNC = "sync", Prompt.LIST
    DOWNLOAD = "download", Prompt.LIST
    CONVERT = "convert", Prompt.LIST
    QUIT = "quit", Prompt.LIST
    UTILS = "utils", Prompt.LIST
    SETTINGS = "settings", Prompt.LIST

    MAIN_OPT = [DOWNLOAD, SYNC, CONVERT, UTILS, SETTINGS, QUIT]

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
    SETTINGS_Q = "settings"
    DOWNLOAD_SETTINGS = "downloads"
    DATABASE_SETTINGS = "database"
    HELP = "help"
    BACK = "back"
    SETTINGS_OPT = [
        DOWNLOAD_SETTINGS,
        DATABASE_SETTINGS,
        HELP,
        BACK,
    ]

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


class UtilsMenu(MenuBase):
    UTILS_Q = "utils"
    MANAGE_SELECTED_PLAYLIST = "manage selected playlist"
    CLEAN_TMP = "clean tmp files"
    REFRESH_SESSION = "refresh tidal session"
    TIDEKEEPER_DOCTOR = "run tidekeeper doctor"
    RUN_WATCHER = "run local files watcher (update db)"
    WATCH_PLAYLIST_FILES = "watch playlist files (update db)"
    CONVERT_TO_FLAC = "convert non-flac files to flac"
    FIX_MISSING_DATA = "fix missing data (update db)"
    BACK = "back"
    UTILS_OPT = [
        MANAGE_SELECTED_PLAYLIST,
        CLEAN_TMP,
        REFRESH_SESSION,
        TIDEKEEPER_DOCTOR,
        RUN_WATCHER,
        WATCH_PLAYLIST_FILES,
        CONVERT_TO_FLAC,
        FIX_MISSING_DATA,
        BACK,
    ]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = self.UTILS_OPT

    def display(self):
        questions = [
            {
                "type": "list",
                "name": "action",
                "message": self.UTILS_Q,
                "choices": self.options,
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("action")


class DownloadSettingsMenu(MenuBase):
    DOWNLOAD_DIR = "download directory"
    AUDIO_QUALITY = "audio quality"
    AUTO_MP3 = "automatic mp3 conversion"
    TIDEKEEPER_SETTINGS = "tidekeeper additional settings"
    BACK = "back"
    OPTIONS = [DOWNLOAD_DIR, AUDIO_QUALITY, AUTO_MP3, TIDEKEEPER_SETTINGS, BACK]

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self):
        questions = [{
            "type": "list", "name": "action", "message": "download settings",
            "choices": self.OPTIONS, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        return prompt(questions).get("action")


class DatabaseSettingsMenu(MenuBase):
    ENABLED = "database enabled"
    DATABASE_PATH = "database location path"
    FLAC_DIR = "flac directory"
    MP3_DIR = "mp3 directory"
    OTHER_LOCATIONS = "other locations"
    BACK = "back"
    OPTIONS = [
        ENABLED,
        DATABASE_PATH,
        FLAC_DIR,
        MP3_DIR,
        OTHER_LOCATIONS,
        BACK,
    ]

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self):
        questions = [{
            "type": "list", "name": "action", "message": "database settings",
            "choices": self.OPTIONS, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        return prompt(questions).get("action")


class TidekeeperSettingsMenu(MenuBase):
    OPTIONS = [
        "includeEP", "saveCovers", "language", "lyricFile", "apiKeyIndex",
        "showProgress", "showTrackInfo", "saveAlbumInfo", "multiThread",
        "downloadDelay", "requestIntervalSeconds", "adaptiveRateLimit",
        "albumFolderFormat", "trackFileFormat", "back",
    ]

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self):
        questions = [{
            "type": "list", "name": "action", "message": "tidekeeper additional settings",
            "choices": self.OPTIONS, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        return prompt(questions).get("action")


class DefaultSelectionMenu(MenuBase):
    VIEW = "view selection"
    REFRESH = "refresh selection stats"
    CHANGE = "change selection"
    BACK = "back"
    OPTIONS = [VIEW, REFRESH, CHANGE, BACK]

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self):
        questions = [{
            "type": "list", "name": "action",
            "message": "playlists default selection",
            "choices": self.OPTIONS, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        return prompt(questions).get("action")


class DownloadDirMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.INPUT)

    def display(self, current: str = None, message="download directory"):
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
        message = "download quality"
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


class AudioQualityMenu(MenuBase):
    OPTIONS = ["Max", "HiFi", "High", "Normal"]
    FALLBACK_OPTIONS = ["None", *OPTIONS]

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self, target=None, fallback=None):
        questions = [
            {
                "type": "list", "name": "target", "message": "target audio quality",
                "choices": self.OPTIONS, "default": target or "Max",
                "mandatory": False, "keybindings": BACK_KEYBINDINGS,
            },
            {
                "type": "list", "name": "fallback", "message": "fallback quality",
                "choices": self.FALLBACK_OPTIONS, "default": fallback or "HiFi",
                "mandatory": False, "keybindings": BACK_KEYBINDINGS,
            },
        ]
        return prompt(questions)


class ToggleMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self, message, enabled=True):
        questions = [{
            "type": "list", "name": "value", "message": message,
            "choices": ["enable", "disable"],
            "default": "enable" if enabled else "disable",
            "mandatory": False, "keybindings": BACK_KEYBINDINGS,
        }]
        return prompt(questions).get("value")


class SaveSelectionMenu(MenuBase):
    SAVE_SELECTION_Q = "save selection?"
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
    SELECTION_Q = "how do you want to proceed?"
    SEARCH = "search", Prompt.SEARCH
    SELECT = "new playlist selection", Prompt.LIST
    BACK = "back", Prompt.LIST
    URL = "url"
    LOAD = "load selection"
    SELECTION_OPT = [SEARCH, SELECT, BACK]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = [
            opt[0] for opt in self.SELECTION_OPT
        ]

    def display(self, include_url=False):
        options = ([self.URL] if include_url else []) + [self.SEARCH[0], self.SELECT[0]]
        if include_url:
            options.append(self.LOAD)
        options.append(self.BACK[0])
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
                "message": "tidal or spotify url",
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = prompt(questions)
        return response.get("url")


class SelectMenu(MenuBase):
    SELECT_Q = "select playlists (all = a, none = n)"
    SELECT_ERR = "select at least one playlist"

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.playlists = None

    def display(self, playlists: list, selected=None):
        selected = set(selected or [])
        choices = [
            {"name": playlist, "value": playlist, "enabled": playlist in selected}
            for playlist in playlists
        ]
        keybindings_select_list = {
            "toggle-all-true": [{"key": "a"}],
            "toggle-all-false": [{"key": "n"}],
        }
        questions = [
            {
                "type": "checkbox",
                "message": self.SELECT_Q,
                "name": "selected_playlists",
                "choices": choices,
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
                "message": "search",
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
