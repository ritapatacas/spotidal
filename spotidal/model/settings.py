import os

from ..model.helpers.td_downloader import default_Settings, check_login
from .helpers.type.file import Files

# Tidekeeper's Max tier maps to Tidal's HI_RES output (up to 24 bit, 192 kHz).
QUALITY_OPTIONS = ["Max", "HiFi", "High", "Normal"]
DEFAULT_QUALITY = "Max"
DEFAULT_DOWNLOAD_PATH = "~/Spotidal"
DEFAULTS = {
    "qualityFallback": "HiFi",
    "autoConvertMp3": True,
    "databaseEnabled": True,
    "watcherEnabled": True,
    "otherLocations": [],
    "tidekeeper": {
        "includeEP": False,
        "saveCovers": True,
        "language": "en",
        "lyricFile": False,
        "apiKeyIndex": 0,
        "showProgress": True,
        "showTrackInfo": True,
        "saveAlbumInfo": True,
        "multiThread": True,
        "downloadDelay": False,
        "requestIntervalSeconds": 1,
        "adaptiveRateLimit": True,
        "albumFolderFormat": "{ArtistName}/{AlbumTitle}",
        "trackFileFormat": "{TrackNumber} - {ArtistName} - {TrackTitle}",
    },
}


class Settings:

    def reset_settings(self):
        default_Settings()
        Files.SETTINGS.save(
            {
                "audioQuality": DEFAULT_QUALITY,
                "downloadPath": DEFAULT_DOWNLOAD_PATH,
                **DEFAULTS,
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
        changed = False
        for key, value in DEFAULTS.items():
            if key not in settings:
                settings[key] = value
                changed = True
        if "flacDirectory" not in settings:
            settings["flacDirectory"] = os.path.join(
                settings["downloadPath"], "flac"
            )
            changed = True
        if "mp3Directory" not in settings:
            settings["mp3Directory"] = os.path.join(
                settings["downloadPath"], "mp3"
            )
            changed = True
        if "databaseLocation" not in settings:
            settings["databaseLocation"] = os.path.join(
                settings["downloadPath"], "database", "library.db"
            )
            changed = True
        if changed:
            Files.SETTINGS.save(settings)
        return settings

    def get_download_dir(self):
        return os.path.abspath(os.path.expanduser(self.get_settings().get("downloadPath")))

    def get_download_quality(self):
        return self.get_settings().get("audioQuality")

    def get_quality_fallback(self):
        return self.get_settings().get("qualityFallback")

    def get_flac_dir(self):
        return os.path.abspath(os.path.expanduser(self.get_settings()["flacDirectory"]))

    def get_mp3_dir(self):
        return os.path.abspath(os.path.expanduser(self.get_settings()["mp3Directory"]))

    def get_database_path(self):
        return os.path.abspath(os.path.expanduser(self.get_settings()["databaseLocation"]))

    def get_other_locations(self):
        return self.get_settings().get("otherLocations", [])

    def get_database_enabled(self):
        return self.get_settings().get("databaseEnabled", True)

    def get_watcher_enabled(self):
        return self.get_settings().get("watcherEnabled", True)

    def set_option(self, key, value):
        settings = self.get_settings()
        settings[key] = value
        Files.SETTINGS.save(settings)
        return value

    def set_download_dir(self, path: str):
        old_path = self.get_download_dir()
        path = os.path.abspath(os.path.expanduser(path.strip()))
        settings = self.get_settings()
        settings["downloadPath"] = path
        if os.path.abspath(os.path.expanduser(settings["flacDirectory"])) == os.path.join(old_path, "flac"):
            settings["flacDirectory"] = os.path.join(path, "flac")
        if os.path.abspath(os.path.expanduser(settings["mp3Directory"])) == os.path.join(old_path, "mp3"):
            settings["mp3Directory"] = os.path.join(path, "mp3")
        if os.path.abspath(os.path.expanduser(settings["databaseLocation"])) == os.path.join(old_path, "database", "library.db"):
            settings["databaseLocation"] = os.path.join(path, "database", "library.db")
        Files.SETTINGS.save(settings)
        return path

    def set_download_quality(self, quality: str):
        if quality not in QUALITY_OPTIONS:
            raise ValueError(f"invalid quality: {quality}")
        settings = self.get_settings()
        settings["audioQuality"] = quality
        Files.SETTINGS.save(settings)
        return quality

    def set_quality_fallback(self, quality):
        if quality not in ["None", *QUALITY_OPTIONS]:
            raise ValueError(f"invalid fallback quality: {quality}")
        return self.set_option("qualityFallback", quality)
