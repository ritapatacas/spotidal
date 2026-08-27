import shutil
import subprocess
import sys
from pathlib import Path

from .library import MusicLibrary


def convert_file(flac_file, output_file, library_root=None):
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
            "-q:a",
            "0",
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
        print(f"> failed to convert {flac_file}: {error}")
        return False
    if library_root:
        library = MusicLibrary(library_root)
        track_id = library.import_file(flac_file)
        library.write_track_id(output_file, track_id)
        library.import_file(output_file)
    print(f"> mp3 conversion complete for {output_file}")
    return True


class FlacToMp3:
    def __init__(self, download_path):
        base_path = Path(download_path).expanduser()
        self.library = MusicLibrary(base_path)
        self.flac_path = base_path / "flac"
        self.mp3_path = base_path / "mp3"

    def convert(self):
        if not self.flac_path.is_dir():
            print(f"> FLAC directory not found: {self.flac_path}")
            return
        if not shutil.which("ffmpeg"):
            print("> ffmpeg not found; install ffmpeg to convert FLAC files")
            return

        converted = 0
        skipped = 0
        failed = 0
        for flac_file in self.flac_path.rglob("*.flac"):
            if flac_file.name.startswith("._"):
                skipped += 1
                continue
            output_file = self.mp3_path / flac_file.relative_to(self.flac_path)
            output_file = output_file.with_suffix(".mp3")
            if output_file.exists():
                track_id = self.library.import_file(flac_file)
                self.library.write_track_id(output_file, track_id)
                self.library.import_file(output_file)
                skipped += 1
                continue
            if convert_file(flac_file, output_file, self.library.root_path):
                converted += 1
            else:
                failed += 1

        print(
            f"> converted {converted} FLAC file(s), skipped {skipped} file(s), "
            f"failed {failed} file(s)"
        )


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        raise SystemExit("usage: python -m spotidal.model.flac_to_mp3 FLAC_FILE MP3_FILE [LIBRARY_ROOT]")
    library_root = sys.argv[3] if len(sys.argv) == 4 else None
    convert_file(sys.argv[1], sys.argv[2], library_root)
