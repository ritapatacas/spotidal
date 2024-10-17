from .helpers import download
from .helpers.utils import list_handler
from .helpers.type.file import Files

class Download:
    def __init__(self, sessions):
        self.sp_session = sessions["sp"]
        self.td_session = sessions["td"]
        self.sp_credentials = Files.CREDENTIALS.load()["spotify"]

    def _download_by_td_id(self, td_id):
        download(td_id)

    def by_td_id(self, td_id):
        list_handler(td_id, self._download_by_td_id)