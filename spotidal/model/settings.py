import os

from ..model.helpers.td_downloader import default_Settings, check_login
from .helpers.type.file import Files

# HI_RES_LOSSLESS is Tidal's "MAX" tier (up to 24 bit, 192 kHz)
QUALITY_OPTIONS = ["HI_RES_LOSSLESS", "LOSSLESS", "HIGH", "LOW"]
DEFAULT_QUALITY = "HI_RES_LOSSLESS"


class Settings:

    def reset_settings(self):
        default_Settings()

    def check_tidal_login(self):
        check_login()

    def get_settings(self):
        settings = Files.SETTINGS.load() or {}
        if settings.get("quality_audio") not in QUALITY_OPTIONS:
            settings["quality_audio"] = DEFAULT_QUALITY
            Files.SETTINGS.save(settings)
        return settings

    def get_download_dir(self):
        return self.get_settings().get("download_base_path")

    def get_download_quality(self):
        return self.get_settings().get("quality_audio")

    def set_download_dir(self, path: str):
        path = os.path.expanduser(path.strip())
        settings = self.get_settings()
        settings["download_base_path"] = path
        Files.SETTINGS.save(settings)
        return path

    def set_download_quality(self, quality: str):
        if quality not in QUALITY_OPTIONS:
            raise ValueError(f"invalid quality: {quality}")
        settings = self.get_settings()
        settings["quality_audio"] = quality
        Files.SETTINGS.save(settings)
        return quality
