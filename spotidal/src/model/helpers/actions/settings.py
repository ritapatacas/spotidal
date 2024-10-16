import spotidal.src.model.helpers.td_downloader as downloader


class Settings:

    def reset_settings(self):
        downloader.default_Settings()

    def check_tidal_login(self):
        downloader.check_login()
