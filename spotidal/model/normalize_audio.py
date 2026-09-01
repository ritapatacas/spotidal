import shutil
import subprocess
from pathlib import Path

from .library import MusicLibrary
from ..view.text import Text as t

CONVERTIBLE_EXTENSIONS = {".m4a", ".wav", ".aac", ".alac", ".aiff", ".ogg"}
BACKUP_DIR_NAME = ".converted_originals"


def archive_original(source_file, base_dir):
    # Keep the pre-conversion file instead of deleting it, so quality can be
    # spot-checked; it's moved out of the way so scans only ever see .flac.
    source_file = Path(source_file)
    base_dir = Path(base_dir)
    try:
        relative = source_file.relative_to(base_dir)
    except ValueError:
        relative = Path(source_file.name)
    destination = base_dir / BACKUP_DIR_NAME / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_file.replace(destination)
    return destination


def convert_to_flac(source_file, output_file):
    source_file = Path(source_file)
    output_file = Path(output_file)
    if output_file.exists():
        return False
    result = subprocess.run(
        [
            "ffmpeg",
            "-i", str(source_file),
            "-map", "0:a:0",
            "-map_metadata", "0",
            "-codec:a", "flac",
            str(output_file),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output_file.unlink(missing_ok=True)
        errors = result.stderr.strip().splitlines()
        error = errors[-1] if errors else "unknown ffmpeg error"
        print(t.log(f"failed to convert {source_file.name}: {error}"))
        return False
    return True


class NormalizeToFlac:
    def __init__(self, download_path, flac_path=None, database_path=None):
        base_path = Path(download_path).expanduser()
        self.library = MusicLibrary(base_path, database_path)
        self.flac_path = Path(flac_path or base_path / "flac").expanduser()

    def convert(self):
        if not self.flac_path.is_dir():
            print(t.log(f"FLAC directory not found: {self.flac_path}"))
            return
        if not shutil.which("ffmpeg"):
            print(t.log("ffmpeg not found; install ffmpeg to convert files"))
            return

        stray_files = [
            path for path in self.flac_path.rglob("*")
            if path.is_file()
            and path.suffix.lower() in CONVERTIBLE_EXTENSIONS
            and not path.name.startswith("._")
            and BACKUP_DIR_NAME not in path.relative_to(self.flac_path).parts
        ]
        if not stray_files:
            print(t.log("no non-FLAC audio files found"))
            return

        converted = 0
        failed = 0
        for source_file in stray_files:
            output_file = source_file.with_suffix(".flac")
            if not convert_to_flac(source_file, output_file):
                failed += 1
                continue
            try:
                self.library.import_file(output_file)
                archive_original(source_file, self.flac_path)
                converted += 1
                print(t.log(f"converted {source_file.name} -> {output_file.name}"))
            except Exception as error:
                failed += 1
                print(t.error(f"converted but failed to index {output_file.name}: {error}"))

        print(t.log(f"converted {converted} file(s) to FLAC, {failed} failed"))
