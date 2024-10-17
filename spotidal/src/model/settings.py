from ..model.helpers.td_downloader import default_Settings, check_login


class Settings:

    def reset_settings(self):
        default_Settings()

    def check_tidal_login(self):
        check_login()
