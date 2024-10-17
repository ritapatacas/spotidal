from ..helpers.type.file import Files
from spotidal.src.view.text import Text as t


def fetch_parsed_playlists(sp_playlists, td_playlists):
    playlist_dict = {}

    for p in sp_playlists:
        name = p["name"]
        playlist_dict[name] = {"name": name, "sp_id": p["id"], "td_id": None}

    for p in td_playlists:
        name = p.name
        if name in playlist_dict:
            playlist_dict[name]["td_id"] = p.id
        else:
            playlist_dict[name] = {"name": name, "sp_id": None, "td_id": p.id}

    parsed_playlists = list(playlist_dict.values())
    Files.PLAYLISTS.save(parsed_playlists)
    Files.PARSED_PLAYLISTS.save(parsed_playlists)
    return parsed_playlists


def list_handler(reference, action):
    if isinstance(reference, str):
        action(reference)

    elif isinstance(reference, list):
        for r in reference:
            action(r)
    else:
        return TypeError(t.error("arg must be a string or a list of strings"))


def get_saved_selection():
    return Files.SELECTION.load()


def get_parsed_playlists():
    return Files.PLAYLISTS.load()
