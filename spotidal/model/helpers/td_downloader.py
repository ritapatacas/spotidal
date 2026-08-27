import sys
import subprocess
from ..helpers.type.file import Files
from ...view.text import Text as t


def check_and_install_tidal_dl():
    try:
        result = subprocess.run(
            ["tidal-dl-ng", "--version"], capture_output=True, text=True
        )
        print("> tidal-dl-ng installed version", result.stdout)
        if result.returncode != 0:
            raise Exception("> tidal-dl-ng not installed")
    except Exception:
        # the original tidal-dl-ng package was removed from PyPI;
        # tidal-dl-ng-for-dj is a maintained fork providing the same CLI
        print("> tidal-dl-ng not found, installing...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "tidal-dl-ng-for-dj"]
        )


def default_Settings():
    check_and_install_tidal_dl()
    default_settings = Files.DEFAULT_SETTINGS.load()
    Files.SETTINGS.save(default_settings)


def check_login():
    result = subprocess.run(["tidal-dl-ng", "login"], capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)


def download_playlist(playlist_id, timeout=240):
    check_and_install_tidal_dl()

    print(t.log("downloading, please don't close the terminal..."))

    # todo check how many tracks the playlist has

    playlist_link = f"https://tidal.com/browse/playlist/{playlist_id}"
    command = ["tidal-dl-ng", "dl", playlist_link]

    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout
        )
        print(result.stdout)
        print(result.stderr)
    except subprocess.TimeoutExpired:
        print(
            f"> timed out after {timeout} seconds.\n> please go to settings > download troubleshooting"
        )
