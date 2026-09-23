#!/usr/bin/env python3
"""
End-to-end runner: builds the flac-match reports for compilations and
EPs-et-al (via scan_missing_flac.py), then runs download_missing_flac.py
for all three sources (albums, compilations, EPs-et-al) at once, in
separate subprocesses so they don't block each other. Each source's
output is interleaved to this terminal with a colored "[source]" tag so
you can tell them apart; each still keeps its own resumable progress
file, same as running them by hand in separate terminals.

Usage:
    poetry run python scripts/run_missing_flac_pipeline.py
    poetry run python scripts/run_missing_flac_pipeline.py --skip-scan   # reports already built
    poetry run python scripts/run_missing_flac_pipeline.py --only compilations,eps
"""
import argparse
import subprocess
import sys
import threading
from pathlib import Path

SOUND_LIBRARY = Path("/Users/ritapatacas/sound-library")
SCRIPTS_DIR = Path(__file__).resolve().parent

GREY = "\033[38;5;102m"
WHITE = "\033[0m"

SOURCES = {
    "albums": {
        "report": SOUND_LIBRARY / "flac_match_report.csv",
        "scan_dir": None,  # pre-existing report, no scan needed
        "color": "\033[38;5;75m",   # blue
    },
    "compilations": {
        "report": SOUND_LIBRARY / "compilations_flac_match_report.csv",
        "scan_dir": SOUND_LIBRARY / "lib" / "compilations",
        "color": "\033[38;5;186m",  # yellow
    },
    "eps": {
        "report": SOUND_LIBRARY / "eps_flac_match_report.csv",
        "scan_dir": SOUND_LIBRARY / "lib" / "EPs-et-al",
        "color": "\033[95m",        # purple
    },
}

print_lock = threading.Lock()


def _grey(text):
    return GREY + text + WHITE


def run_scan(name: str, info: dict):
    print(_grey(f"==> scanning {info['scan_dir']} for existing flacs"))
    subprocess.run(
        [
            sys.executable, str(SCRIPTS_DIR / "scan_missing_flac.py"),
            "--source-dir", str(info["scan_dir"]),
            "--out", str(info["report"]),
        ],
        check=True,
    )


def stream_download(name: str, info: dict):
    tag = f"{info['color']}[{name}]{WHITE}"
    process = subprocess.Popen(
        [
            sys.executable, str(SCRIPTS_DIR / "download_missing_flac.py"),
            "--report", str(info["report"]),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    for line in process.stdout:
        with print_lock:
            print(f"{tag} {line.rstrip()}")
    process.wait()
    with print_lock:
        print(_grey(f"==> {name} finished (exit code {process.returncode})"))
    return process.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", default="albums,compilations,eps",
        help="comma-separated subset of: albums,compilations,eps",
    )
    parser.add_argument(
        "--skip-scan", action="store_true",
        help="reports already exist; skip scan_missing_flac.py",
    )
    args = parser.parse_args()

    names = [n.strip() for n in args.only.split(",") if n.strip()]
    unknown = set(names) - set(SOURCES)
    if unknown:
        raise SystemExit(f"unknown source(s): {', '.join(unknown)} (choose from {', '.join(SOURCES)})")

    if not args.skip_scan:
        for name in names:
            info = SOURCES[name]
            if info["scan_dir"] is not None:
                run_scan(name, info)

    for name in names:
        info = SOURCES[name]
        if not info["report"].exists():
            raise SystemExit(f"report missing for {name}: {info['report']} (run without --skip-scan first)")

    print(_grey(f"==> starting downloads for: {', '.join(names)}"))

    threads = []
    results = {}

    def _run(name):
        results[name] = stream_download(name, SOURCES[name])

    for name in names:
        thread = threading.Thread(target=_run, args=(name,), daemon=True)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    print(_grey(f"==> all done: {results}"))


if __name__ == "__main__":
    main()
