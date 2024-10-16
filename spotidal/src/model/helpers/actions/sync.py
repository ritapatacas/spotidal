import spotidal.src.model.helpers.utils as utils
import spotidal.src.model.helpers.synchronizer as _sync
from spotidal.src.model.helpers.type.file import Files


class Sync:
    def __init__(self, sessions):
        self.sessions = sessions
        self.sp_credentials = Files.CREDENTIALS.load()["spotify"]


    def _sync_playlist(self, sp_id):
        sp_playlist = self.sessions["sp"].playlist(sp_id)
        td_playlists = _sync._playlists.get_td_playlists_wrapper(self.sessions["td"])
        td_playlist = _sync._search.pick_td_playlist_for_sp_playlist(
            sp_playlist, td_playlists
        )
        _sync.sync_playlists_wrapper(
            self.sessions["sp"], self.sessions["td"], [td_playlist], self.sp_credentials
        )

    def by_sp_id(self, sp_id):
        utils.list_handler(sp_id, self._sync_playlist)

    def by_name(self, name):
        def action(n):
            self._sync_playlist(utils.convert.name_to["ids"](n)[0])

        utils.list_handler(name, action)

    def saved_selection(self):
        selection = utils.file.load_saved_selection()

        for playlist in selection:
            self._sync_playlist(playlist["sp_id"])
