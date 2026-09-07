import shutil
import subprocess
import sys
from pathlib import Path

from .library import MusicLibrary, uuid7
from ..view.text import Text as t


def convert_file(flac_file, output_file, library_root=None, database_path=None):
    flac_file = Path(flac_file)
    output_file = Path(output_file)
    if output_file.exists():
        return False
    output_file.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(flac_file),
            "-map",
            "0:a:0",
            "-map",
            "0:v?",
            "-map_metadata",
            "0",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "320k",
            "-c:v",
            "copy",
            "-id3v2_version",
            "3",
            str(output_file),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output_file.unlink(missing_ok=True)
        errors = result.stderr.strip().splitlines()
        error = errors[-1] if errors else "unknown ffmpeg error"
        print(t.log(f"failed to convert {flac_file}: {error}"))
        return False
    if library_root:
        library = MusicLibrary(library_root, database_path)
        library.import_file(flac_file)
        _import_mp3_with_own_track_id(library, output_file)
    print(t.log(f"mp3 conversion complete for {output_file}"))
    return True


def _import_mp3_with_own_track_id(library, mp3_file):
    # Each mp3 conversion gets its own track_id (distinct from the source
    # flac's), so converting doesn't collapse two library rows into one.
    if not library.read_track_id(mp3_file):
        library.write_track_id(mp3_file, uuid7())
    return library.import_file(mp3_file)


class FlacToMp3:
    def __init__(self, download_path, flac_path=None, mp3_path=None, database_path=None):
        base_path = Path(download_path).expanduser()
        self.library = MusicLibrary(base_path, database_path)
        self.database_path = database_path
        self.flac_path = Path(flac_path or base_path / "flac").expanduser()
        self.mp3_path = Path(mp3_path or base_path / "mp3").expanduser()

    def _mp3_target(self, flac_file):
        return (
            self.mp3_path / flac_file.relative_to(self.flac_path)
        ).with_suffix(".mp3")

    def _count_audio(self, root, extension):
        if not root.is_dir():
            return 0
        return sum(
            1
            for audio_file in root.rglob(extension)
            if not audio_file.name.startswith("._")
        )

    def convert(self):
        if not self.flac_path.is_dir():
            print(t.log(f"FLAC directory not found: {self.flac_path}"))
            return
        if not shutil.which("ffmpeg"):
            print(t.log("ffmpeg not found; install ffmpeg to convert FLAC files"))
            return

        # AppleDouble sidecars (._*) on exFAT volumes would otherwise show up
        # as a bogus "skipped" the size of the whole library.
        flac_files = [
            flac_file
            for flac_file in self.flac_path.rglob("*.flac")
            if not flac_file.name.startswith("._")
        ]
        pending = [
            flac_file for flac_file in flac_files
            if not self._mp3_target(flac_file).exists()
        ]
        already_converted = len(flac_files) - len(pending)
        print(t.log(
            f"{len(flac_files)} FLAC file(s) found, {len(pending)} to convert "
            f"({already_converted} already have an mp3)"
        ))

        converted = 0
        reindexed = 0
        failed = 0
        for flac_file in flac_files:
            output_file = self._mp3_target(flac_file)
            if output_file.exists():
                self.library.import_file(flac_file)
                _import_mp3_with_own_track_id(self.library, output_file)
                reindexed += 1
                continue
            if convert_file(
                flac_file, output_file, self.library.root_path, self.database_path
            ):
                converted += 1
            else:
                failed += 1

        summary = (
            f"converted {converted} FLAC file(s) in this run | "
            f"library now: {len(flac_files)} flac, "
            f"{self._count_audio(self.mp3_path, '*.mp3')} mp3"
        )
        if already_converted:
            summary += f" ({already_converted} mp3 already existed, {reindexed} re-indexed)"
        if failed:
            summary += f", {failed} failed"
        print(t.log(summary))


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4, 5):
        raise SystemExit("usage: python -m spotidal.model.flac_to_mp3 FLAC_FILE MP3_FILE [LIBRARY_ROOT] [DATABASE_PATH]")
    library_root = sys.argv[3] if len(sys.argv) >= 4 else None
    database_path = sys.argv[4] if len(sys.argv) == 5 else None
    convert_file(sys.argv[1], sys.argv[2], library_root, database_path)
