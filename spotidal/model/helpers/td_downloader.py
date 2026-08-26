import sys
import subprocess
import shutil
import threading
from ..helpers.type.file import Files
from ...view.text import Text as t


def check_and_install_tidal_dl():
    for command in ("tidal-dl-ng", "tidekeeper", "tidal-dl"):
        if shutil.which(command):
            return command

    # tidal-dl-ng is no longer published reliably for all Python versions.
    # tidekeeper is the maintained Python 3.10+ fork of Tidal-Media-Downloader.
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "tidekeeper"]
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "Não foi possível instalar o downloader do Tidal. "
            "Instala-o manualmente com 'python -m pip install -U tidekeeper'."
        ) from error
    if not shutil.which("tidekeeper"):
        raise RuntimeError("O downloader foi instalado, mas o comando tidekeeper não foi encontrado.")
    return "tidekeeper"


def default_Settings():
    check_and_install_tidal_dl()
    default_settings = Files.DEFAULT_SETTINGS.load()
    Files.SETTINGS.save(default_settings)


def check_login():
    result = subprocess.run(["tidal-dl-ng", "login"], capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)


def download_playlist(playlist_id, timeout=240, output_callback=None):
    downloader = check_and_install_tidal_dl()

    print(t.log("downloading, please don't close the terminal..."))

    # todo check how many tracks the playlist has

    playlist_link = f"https://tidal.com/browse/playlist/{playlist_id}"
    # tidekeeper uses the modern --link interface; retain compatibility with
    # the older tidal-dl-ng command when it is already installed.
    command = [downloader, "dl", playlist_link] if downloader == "tidal-dl-ng" else [downloader, "-l", playlist_link]

    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        def read_output():
            for line in process.stdout:
                print(line, end="")
                if output_callback:
                    output_callback(line.rstrip())

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        try:
            process.wait(timeout=timeout)
        finally:
            if process.poll() is None:
                process.kill()
            reader.join(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        print(
            f"> timed out after {timeout} seconds.\n> please go to settings > download troubleshooting"
        )
