from .helpers.utils import list_handler
from .helpers.synchronizer import sync_playlists_wrapper
from .helpers.sync.playlists_handler import get_td_playlists_wrapper
from .helpers.type.file import Files
from .helpers.sync.search import pick_td_playlist_for_sp_playlist

class Sync:
    def __init__(self, sessions):
        self.sessions = sessions
        self.sp_credentials = Files.CREDENTIALS.load()["spotify"]


    def _sync_playlist(self, sp_id):
        sp_playlist = self.sessions["sp"].playlist(sp_id)
        td_playlists = get_td_playlists_wrapper(self.sessions["td"])
        td_playlist = pick_td_playlist_for_sp_playlist(
            sp_playlist, td_playlists
        )
        sync_playlists_wrapper(
            self.sessions["sp"], self.sessions["td"], [td_playlist], self.sp_credentials
        )
        return td_playlist

    def by_sp_id(self, sp_id):
        if isinstance(sp_id, str):
            return self._sync_playlist(sp_id)
        return list_handler(sp_id, self._sync_playlist)

    def saved_selection(self):
        selection = Files.SELECTION.load()

        for playlist in selection:
            self._sync_playlist(playlist["sp_id"])
