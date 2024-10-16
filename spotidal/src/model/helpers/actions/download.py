import spotidal.src.model.helpers.utils as utils
import spotidal.src.model.helpers.td_downloader as downloader
from spotidal.src.model.helpers.type.file import Files


class Download:
    def __init__(self, sessions):
        self.sp_session = sessions["sp"]
        self.td_session = sessions["td"]
        self.sp_credentials = Files.CREDENTIALS.load()["spotify"]

    def _download_by_td_id(self, td_id):
        downloader.download_playlist(td_id)

    def by_td_id(self, td_id):
        utils.list_handler(td_id, self._download_by_td_id)

    def by_sp_id(self, sp_id):
        def action(n):
            self._download_by_td_id(utils.convert.sp_id_to_td_id(n))

        utils.list_handler(sp_id, action)

    def by_name(self, name):
        def action(n):
            self._download_by_td_id(utils.convert.name_to_td_id(n))

        utils.list_handler(name, action)

    def saved_selection(self):
        selected_playlists = utils.file.load_saved_selection()

        for p in selected_playlists:
            if p["td_id"]:
                self._download_by_td_id(p["td_id"])
            else:
                self.by_name(p["name"])
