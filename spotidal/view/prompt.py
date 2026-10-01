from enum import Enum
from InquirerPy import prompt


def _ask(questions, **kwargs):
    try:
        return prompt(questions, **kwargs)
    except KeyboardInterrupt:
        return {}


BACK_KEYBINDINGS = {"skip": [{"key": "escape"}]}
CONFIRM_KEYBINDINGS = {
    "confirm": [{"key": "y"}, {"key": "Y"}, {"key": "1"}],
    "reject": [{"key": "n"}, {"key": "N"}, {"key": "0"}],
}


class Submenu:
    def __init__(self, title, options):
        self.title = title
        self.options = list(options) + ["back"]

    def display(self):
        questions = [{
            "type": "list", "name": "action", "message": self.title,
            "choices": self.options, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        action = _ask(questions).get("action")
        return None if action == "back" else action


class InputMenu:
    def __init__(self, message):
        self.message = message

    def display(self):
        questions = [{
            "type": "input", "name": "value", "message": self.message,
            "mandatory": False, "keybindings": BACK_KEYBINDINGS,
        }]
        return _ask(questions).get("value")


class ListMenu:
    def __init__(self, title, options):
        self.title = title
        self.options = list(options)

    def display(self):
        questions = [{
            "type": "list", "name": "action", "message": self.title,
            "choices": self.options, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        return _ask(questions).get("action")


class Prompt(Enum):
    LIST = "list"
    SEARCH = "fuzzy"
    CONFIRM = "confirm"

    kb_confirm = CONFIRM_KEYBINDINGS
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
    SEARCH = "explore library", Prompt.LIST
    EXPORT_REKORDBOX = "export to rekordbox", Prompt.LIST
    QUIT = "quit", Prompt.LIST
    UTILS = "utils", Prompt.LIST
    SETTINGS = "settings", Prompt.LIST

    MAIN_OPT = [DOWNLOAD, SYNC, SEARCH, CONVERT, EXPORT_REKORDBOX, UTILS, SETTINGS, QUIT]

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
        response = _ask(questions)
        return response.get("action")


class SettingsMenu(MenuBase):
    SETTINGS_Q = "settings"
    DOWNLOAD_SETTINGS = "downloads"
    DATABASE_SETTINGS = "database"
    NOTIFICATIONS_SETTINGS = "notifications"
    HELP = "help"
    BACK = "back"
    SETTINGS_OPT = [
        DOWNLOAD_SETTINGS,
        DATABASE_SETTINGS,
        NOTIFICATIONS_SETTINGS,
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
        response = _ask(questions)
        return response.get("action")


class UtilsMenu(MenuBase):
    UTILS_Q = "utils"
    MANAGE_SELECTED_PLAYLIST = "manage selected playlist"
    CLEAN_TMP = "clean tmp files"
    REFRESH_SESSION = "refresh tidal session"
    TIDEKEEPER_DOCTOR = "run tidekeeper doctor"
    DOCTOR_DOWNLOAD = "download doctor (full pipeline check)"
    DOCTOR_PLAYLISTS = "playlists doctor (tidal sync status, offers refresh)"
    DOCTOR_MISSING_TRACKS = "missing tracks doctor (tidal vs local, download missing)"
    DOCTOR_MP3_QUALITY = "mp3 quality doctor (bitrate vs flac)"
    RUN_WATCHER = "run local files watcher (disk vs db)"
    WATCH_PLAYLIST_FILES = "refresh playlist tracks from tidal (update db)"
    CONVERT_TO_FLAC = "convert non-flac files to flac"
    FIX_MISSING_DATA = "fix missing data (update db)"
    SYNC_DATABASE = "sync database (disk + tidal playlists + repair)"
    FILL_GENRES = "fill genres from discogs (tags+db)"
    FILL_GENRES_RYM = "fill genres from rate your music (browser)"
    IMPORT_REKORDBOX_BPM_KEY = "import bpm/key from rekordbox (update db)"
    AUDIT_CONSISTENCY = "audit playlist consistency (spotify vs local, deep check)"
    BACK = "back"

    PLAYLISTS = "playlists doctors"
    DOCTORS = "doctors"
    DOWNLOAD = "download doctors"
    LOCAL_FILES = "local files doctors"
    DATABASE = "database doctors"
    GENRES = "genres"
    UTILS_OPT = [
        SYNC_DATABASE, MANAGE_SELECTED_PLAYLIST, GENRES, DOCTORS,
    ]

    DOCTORS_OPT = [PLAYLISTS, DOWNLOAD, DATABASE, LOCAL_FILES]

    PLAYLISTS_OPT = [
        DOCTOR_PLAYLISTS, AUDIT_CONSISTENCY,
    ]
    DOWNLOAD_OPT = [
        DOCTOR_DOWNLOAD, DOCTOR_MISSING_TRACKS, TIDEKEEPER_DOCTOR,
        CLEAN_TMP, REFRESH_SESSION,
    ]
    LOCAL_FILES_OPT = [
        DOCTOR_MP3_QUALITY, CONVERT_TO_FLAC, RUN_WATCHER,
    ]
    DATABASE_OPT = [
        DOCTOR_PLAYLISTS, RUN_WATCHER, WATCH_PLAYLIST_FILES,
        FIX_MISSING_DATA, FILL_GENRES, IMPORT_REKORDBOX_BPM_KEY,
    ]
    VIEW_GENRES = "view genres"
    VIEW_GENRE_STYLES = "view genre styles"
    ADD_GENRE_STYLE = "add genre and/or style"
    GENRES_OPT = [
        VIEW_GENRES, VIEW_GENRE_STYLES, ADD_GENRE_STYLE,
        FILL_GENRES, FILL_GENRES_RYM,
    ]
    ALL_GENRES = "all genres"
    SELECT_GENRE = "select genre"
    VIEW_STYLES_OPT = [ALL_GENRES, SELECT_GENRE]
    FILL_SELECTED = "selected"
    FILL_ALL = "all"
    FILL_SELECT_PLAYLISTS = "select playlists"
    FILL_GENRES_OPT = [FILL_SELECTED, FILL_SELECT_PLAYLISTS]
    FILL_RYM_OPT = [FILL_SELECTED, FILL_ALL, FILL_SELECT_PLAYLISTS]

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
        try:
            response = _ask(questions)
        except KeyboardInterrupt:
            return None
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
        return _ask(questions).get("action")


class MissingTracksModeMenu(MenuBase):
    DOWNLOAD = "download current missing tracks"
    FIND = "find missing tracks"
    FIND_AND_DOWNLOAD = "find and download missing tracks"
    BACK = "back"
    OPTIONS = [FIND_AND_DOWNLOAD, FIND, DOWNLOAD, BACK]

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self):
        questions = [{
            "type": "list", "name": "action", "message": "missing tracks doctor",
            "choices": self.OPTIONS, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        return _ask(questions).get("action")


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
        return _ask(questions).get("action")


class NotificationsSettingsMenu(MenuBase):
    SOUND_DELAY = "notification sound delay (minutes)"
    BACK = "back"
    OPTIONS = [SOUND_DELAY, BACK]

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self):
        questions = [{
            "type": "list", "name": "action", "message": "notifications",
            "choices": self.OPTIONS, "mandatory": False,
            "keybindings": BACK_KEYBINDINGS,
        }]
        return _ask(questions).get("action")


class NotificationDelayMenu(MenuBase):
    def __init__(self):
        super().__init__(Prompt.INPUT)

    def display(self, current=None):
        message = "play a sound when a task takes longer than (minutes, 0 disables)"
        questions = [{
            "type": "input",
            "name": "value",
            "message": f"{message} (current: {current})",
            "default": str(current) if current is not None else "5",
            "keybindings": BACK_KEYBINDINGS,
        }]
        return _ask(questions).get("value")


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
        return _ask(questions).get("action")


class DefaultSelectionMenu(MenuBase):
    VIEW = "view selection (tidal vs local stats)"
    REFRESH = "refresh selection stats (tidal vs local)"
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
        return _ask(questions).get("action")


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
        response = _ask(questions)
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
        response = _ask(questions)
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
        return _ask(questions)


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
        return _ask(questions).get("value")


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
                "keybindings": {**BACK_KEYBINDINGS, **CONFIRM_KEYBINDINGS},
            }
        ]
        response = _ask(questions)
        return response.get("save_selection")


class SelectionModeMenu(MenuBase):
    SELECTION_Q = "how do you want to proceed?"
    SEARCH = "search", Prompt.SEARCH
    SELECT = "new playlist selection", Prompt.LIST
    BACK = "back", Prompt.LIST
    URL = "url"
    LOAD = "load selection"
    DOWNLOAD_MISSING = "download current missing tracks"
    SELECTION_OPT = [SEARCH, SELECT, BACK]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = [
            opt[0] for opt in self.SELECTION_OPT
        ]

    def display(self, include_url=False, include_missing_tracks=False):
        options = (
            ([self.DOWNLOAD_MISSING] if include_missing_tracks else [])
            + ([self.LOAD] if include_url else [])
            + [self.SELECT[0], self.SEARCH[0]]
        )
        if include_url:
            options.append(self.URL)
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
        response = _ask(questions)
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
        response = _ask(questions)
        return response.get("url")


class SelectMenu(MenuBase):
    SELECT_Q = "select playlists (all = a, none = n, invert = i, back = b, save = s)"
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
            "toggle-all": [{"key": "i"}],
            "answer": [{"key": "enter"}, {"key": "s"}],
            "skip": [{"key": "escape"}, {"key": "b"}],
        }
        questions = [
            {
                "type": "checkbox",
                "message": self.SELECT_Q,
                "name": "selected_playlists",
                "choices": choices,
                "mandatory": False,
                "transformer": lambda result: (
                    f"{len(result)} selected: {', '.join(result)}" if result else "none"
                ),
            }
        ]
        response = _ask(questions, keybindings=keybindings_select_list)
        if not response.get("selected_playlists"):
            print(self.SELECT_ERR)
        return response.get("selected_playlists")


class OriginalAlbumMenu(MenuBase):
    USE_SPOTIFY = "use the spotify versions"
    USE_ORIGINAL = "use the original album versions"
    REVIEW = "review the list"
    CHOICE_OPT = [USE_SPOTIFY, USE_ORIGINAL, REVIEW]

    def __init__(self):
        super().__init__(Prompt.LIST)
        self.options = self.CHOICE_OPT

    def display(self, count):
        questions = [
            {
                "type": "list",
                "name": "action",
                "message": f"{count} track(s) matched from a non-original album — what do you want to do?",
                "choices": self.options,
                "mandatory": False,
                "keybindings": BACK_KEYBINDINGS,
            }
        ]
        response = _ask(questions)
        return response.get("action")


class OriginalAlbumReviewMenu(MenuBase):
    REVIEW_Q = "pick which to use as original (all original = a, all spotify = n, cancel = c, confirm = enter)"

    def __init__(self):
        super().__init__(Prompt.LIST)

    def display(self, choices):
        items = [
            {
                "name": (
                    f"{c['spotify_track'].artist.name} - {c['spotify_track'].name}  |  "
                    f"spotify: {c['spotify_track'].album.name}  ->  original: {c['original_track'].album.name}"
                ),
                "value": i,
                "enabled": False,
            }
            for i, c in enumerate(choices)
        ]
        keybindings = {
            "toggle-all-true": [{"key": "a"}],
            "toggle-all-false": [{"key": "n"}],
            "answer": [{"key": "enter"}],
            "skip": [{"key": "escape"}, {"key": "c"}],
        }
        questions = [
            {
                "type": "checkbox",
                "message": self.REVIEW_Q,
                "name": "use_original",
                "choices": items,
                "mandatory": False,
            }
        ]
        response = _ask(questions, keybindings=keybindings)
        return response.get("use_original")


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
        response = _ask(questions)
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
        response = _ask(questions)
        return response.get("confirm")
