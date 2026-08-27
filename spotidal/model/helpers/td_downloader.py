import os
import subprocess
import sys
import time
from pathlib import Path
from ..helpers.type.file import Files
from ..library import MusicLibrary
from ...view.text import Text as t


QUALITY_PRIORITIES = {
    "Max": "Max,HiFi,High,Normal",
    "Atmos": "Atmos,Max,HiFi,High,Normal",
    "Master": "Master,HiFi,High,Normal",
    "HiFi": "HiFi,High,Normal",
    "High": "High,Normal",
    "Normal": "Normal",
}
DEFAULT_DOWNLOAD_PATH = os.path.expanduser("~/Spotidal2U")


def check_and_install_tidal_dl():
    try:
        result = subprocess.run(
            ["tidekeeper", "--version"], capture_output=True, text=True
        )
        print("> tidekeeper installed version", result.stdout)
        if result.returncode != 0:
            raise Exception("> tidekeeper not installed")
    except Exception:
        print("> tidekeeper not found, installing...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "tidekeeper"]
        )


def default_Settings():
    check_and_install_tidal_dl()


def _remove_partial_files(download_path):
    if not download_path:
        return
    root = Path(os.path.expanduser(download_path))
    if not root.is_dir():
        return
    for _ in range(5):
        partials = list(root.rglob("*.part.parts"))
        if not partials:
            return
        for partial in partials:
            try:
                if partial.is_dir():
                    for directory, directories, files in os.walk(partial, topdown=False):
                        for filename in files:
                            try:
                                os.unlink(os.path.join(directory, filename))
                            except OSError:
                                pass
                        for child in directories:
                            try:
                                os.rmdir(os.path.join(directory, child))
                            except OSError:
                                pass
                    os.rmdir(partial)
                else:
                    partial.unlink()
            except OSError:
                pass
        time.sleep(0.25)


def _flac_files(download_path):
    root = Path(download_path)
    if not root.is_dir():
        return set()
    return {
        file_path
        for file_path in root.rglob("*.flac")
        if not file_path.name.startswith("._")
    }


def _tidal_track_id(url):
    parts = [part for part in url.split("/") if part]
    try:
        index = parts.index("track")
    except ValueError:
        return None
    return parts[index + 1] if index + 1 < len(parts) else None


def _report_downloads(output, download_path, previous_files):
    current_files = _flac_files(download_path)
    reported_files = set()
    for line in output.splitlines():
        if "AccessToken" in line:
            print(t.warning(line.split("] ", 1)[-1]))
        elif "[ERR]" in line:
            print(t.error(line.split("] ", 1)[-1]))
        elif "[SUCCESS]" in line:
            title = line.split("] ", 1)[-1].split(" (skip:", 1)[0].strip()
            matches = [
                file_path
                for file_path in current_files
                if title.lower() in file_path.stem.lower()
            ]
            reported_files.update(matches)

    reported_files.update(current_files - previous_files)
    for file_path in sorted(reported_files):
        print(t.log(f"download complete for {file_path}"))
    return sorted(current_files - previous_files)


def check_login():
    # tidekeeper has no login subcommand; auth happens on first download.
    # --doctor validates config, token, and local tools.
    subprocess.run(["tidekeeper", "--doctor"])


def download_url(url, timeout=240):
    check_and_install_tidal_dl()

    print(t.busy("downloading..."))

    # todo check how many tracks the playlist has

    settings = Files.SETTINGS.load() or {}
    command = [
        "tidekeeper",
        "-q",
        settings.get("audioQuality", "Max"),
        "--quality-priority",
        QUALITY_PRIORITIES.get(
            settings.get("audioQuality", "Max"), "Max,HiFi,High,Normal"
        ),
        "-l",
        url,
    ]
    environment = os.environ.copy()
    download_path = settings.get("downloadPath") or environment.get(
        "TIDEKEEPER_DOWNLOAD_PATH", DEFAULT_DOWNLOAD_PATH
    )
    download_path = os.path.join(os.path.abspath(os.path.expanduser(download_path)), "flac")
    environment["TIDEKEEPER_DOWNLOAD_PATH"] = download_path
    effective_download_path = environment.get("TIDEKEEPER_DOWNLOAD_PATH")
    if effective_download_path:
        command[1:1] = ["-o", effective_download_path]
    previous_files = _flac_files(effective_download_path)

    try:
        result = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        _remove_partial_files(effective_download_path)
        completed_files = _report_downloads(
            output, effective_download_path, previous_files
        )
        library = MusicLibrary(Path(effective_download_path).parent)
        tidal_track_id = _tidal_track_id(url)
        for flac_file in completed_files:
            library.import_file(flac_file, tidal_id=tidal_track_id)
        if result.returncode == 0 and settings.get("autoConvertMp3", True):
            flac_root = Path(effective_download_path)
            mp3_root = flac_root.parent / "mp3"
            for flac_file in completed_files:
                mp3_file = mp3_root / flac_file.relative_to(flac_root)
                mp3_file = mp3_file.with_suffix(".mp3")
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "spotidal.model.flac_to_mp3",
                        str(flac_file),
                        str(mp3_file),
                        str(flac_root.parent),
                    ]
                )
        if result.returncode != 0:
            print("> tidekeeper failed; see its failed-tracks.txt for retryable tracks")
        return completed_files
    except subprocess.TimeoutExpired:
        print(
            f"> timed out after {timeout} seconds.\n> please go to settings > download troubleshooting"
        )
        return []


def download_playlist(playlist_id, timeout=240):
    download_url(f"https://tidal.com/browse/playlist/{playlist_id}", timeout)
