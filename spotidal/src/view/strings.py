from .prompt import Prompt as type

MAIN = "main", type.LIST
SYNC = "sync", type.LIST
DOWNLOAD = "download", type.LIST
SETTINGS = "settings", type.LIST

SEARCH = "search", type.SEARCH
SELECT = "select", type.LIST
BY_ID = "by_id", type.INPUT

SEARCH = "search"
SELECT = "select from list"
BY_ID = "by id"
LOAD = "load saved selection"

BACK = "back"
RESET_SETTINGS = "reset settings"

MAIN_Q = "What do you want to do?"
MAIN_OPT = [SYNC, DOWNLOAD, SETTINGS, BACK]

SETTINGS_Q = "Settings"
SETTINGS_OPT = [RESET_SETTINGS, BACK]
SELECTION_OPT = [SEARCH, SELECT, BY_ID, LOAD, BACK]


PLAYLISTS_Q = "Which playlists?"

SELECT_Q = "Select playlists (all = a, none = n)"
SELECT_ERR = "select at least one playlist"

ID_Q = "Spotify playlist ID to sync"
ID_ERR = "invalid Spotify playlist ID"

ADD_MORE_Q = "Add more or can we proceed?"
SAVE_SELECTION_Q = "Save selection?"

RESET_Q = "Are you sure reset settings?"

SAVED_LOG = "saved"
LOADED_LOG = "loaded"
QUIT_LOG = "quitting!"
