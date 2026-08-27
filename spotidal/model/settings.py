import os

from ..model.helpers.td_downloader import default_Settings, check_login
from .helpers.type.file import Files

# Tidekeeper's Max tier maps to Tidal's HI_RES output (up to 24 bit, 192 kHz).
QUALITY_OPTIONS = ["Max", "Atmos", "Master", "HiFi", "High", "Normal"]
DEFAULT_QUALITY = "Max"
DEFAULT_DOWNLOAD_PATH = "~/Spotidal2U"


class Settings:

    def reset_settings(self):
        default_Settings()
        Files.SETTINGS.save(
            {
                "audioQuality": DEFAULT_QUALITY,
                "downloadPath": DEFAULT_DOWNLOAD_PATH,
                "autoConvertMp3": True,
            }
        )

    def check_tidal_login(self):
        check_login()

    def get_settings(self):
        settings = Files.SETTINGS.load() or {}
        if settings.get("audioQuality") not in QUALITY_OPTIONS:
            settings["audioQuality"] = DEFAULT_QUALITY
            Files.SETTINGS.save(settings)
        if not settings.get("downloadPath"):
            settings["downloadPath"] = DEFAULT_DOWNLOAD_PATH
            Files.SETTINGS.save(settings)
        if "autoConvertMp3" not in settings:
            settings["autoConvertMp3"] = True
            Files.SETTINGS.save(settings)
        return settings

    def get_download_dir(self):
        return os.path.abspath(os.path.expanduser(self.get_settings().get("downloadPath")))

    def get_download_quality(self):
        return self.get_settings().get("audioQuality")

    def set_download_dir(self, path: str):
        path = os.path.abspath(os.path.expanduser(path.strip()))
        settings = self.get_settings()
        settings["downloadPath"] = path
        Files.SETTINGS.save(settings)
        return path

    def set_download_quality(self, quality: str):
        if quality not in QUALITY_OPTIONS:
            raise ValueError(f"invalid quality: {quality}")
        settings = self.get_settings()
        settings["audioQuality"] = quality
        Files.SETTINGS.save(settings)
        return quality
