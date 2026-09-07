import subprocess
import sys

MACOS_SOUNDS = {
    "glass": "/System/Library/Sounds/Glass.aiff",
    "ping": "/System/Library/Sounds/Ping.aiff",
}
DEFAULT_SOUND = "glass"


def play_task_done(sound: str = DEFAULT_SOUND):
    if sys.platform != "darwin":
        return False
    path = MACOS_SOUNDS.get(sound, sound)
    try:
        subprocess.Popen(
            ["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except OSError:
        return False
