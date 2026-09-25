import re
import shutil
from enum import Enum

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


class Colors(Enum):
    RED = "\033[91m"
    RED_BRIGHT = "\033[38;5;132m"
    WHITE = "\033[0m"
    GREEN = "\033[38;5;70m"
    YELLOW = "\033[38;5;186m"
    ORANGE = "\033[38;5;208m"
    BLUE = "\033[38;5;75m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    GREY_BRIGHT = "\033[38;5;249m"
    GREY_MID = "\033[38;5;102m"
    GREY_DARK = "\033[38;5;238m"
    BLACK = "\033[30m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_PURPLE = "\033[45m"

    def __str__(self):
        return self.value


class Text:

    @staticmethod
    def u(text):
        return "\033[4m" + text + str(Colors.WHITE)

    @staticmethod
    def b(text):
        return "\033[1m" + text + str(Colors.WHITE)

    @staticmethod
    def log(text):
        return str(Colors.GREEN) + "> " + str(Colors.WHITE) + text

    @staticmethod
    def log_grey(text):
        return " " + str(Colors.GREY_MID) + "_ " + text
    
    @staticmethod
    def error(text):
        return "\n" + str(Colors.RED) + "! " + str(Colors.WHITE) + text

    @staticmethod
    def warning(text):
        return "\n" + str(Colors.ORANGE) + "! " + str(Colors.WHITE) + text

    @staticmethod
    def grey(text):
        return str(Colors.GREY_MID) + text + str(Colors.WHITE)

    @staticmethod
    def red(text):
        return str(Colors.RED) + text + str(Colors.WHITE)

    @staticmethod
    def right_align(body, tail, min_pad=1, prefix_len=0):
        """Pad `body` with spaces so `tail` lands flush with the terminal's
        right edge, recalculated from the current window width each call
        (rather than a fixed guessed column) so it stays aligned if the
        terminal gets resized. Measures visible width (ANSI color codes
        already embedded in `body`/`tail` don't count), so this works
        whether the caller colors the whole line afterwards or colors
        pieces of it inline.

        `prefix_len` accounts for characters a caller will still prepend
        after this returns (e.g. the "_" a report.info()/log_grey() call
        adds, or the "! " a warning()/error() call adds) — without it the
        line ends up that many columns too wide."""
        columns = shutil.get_terminal_size(fallback=(100, 24)).columns
        visible_body = len(_ANSI_RE.sub("", body))
        visible_tail = len(_ANSI_RE.sub("", tail))
        pad = max(min_pad, columns - prefix_len - visible_body - visible_tail)
        return f"{body}{' ' * pad}{tail}"

    @staticmethod
    def format_elapsed(seconds):
        minutes, secs = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def display_selection(selection):
        start = str(Colors.GREEN) + "> " + str(Colors.WHITE) + "current selection"
        return start + "\n" + "\n".join(f"  {item}" for item in sorted(selection))

    @staticmethod
    def display_selection_table(stats):
        headers = ("playlist", "tracks", "local", "missing")
        rows = [
            (s["name"], str(s["total"]), str(s["local"]), str(s["missing"]))
            for s in stats
        ]
        totals = (
            "total",
            str(sum(s["total"] for s in stats)),
            str(sum(s["local"] for s in stats)),
            str(sum(s["missing"] for s in stats)),
        )
        widths = [
            max(len(headers[i]), len(totals[i]), *(len(row[i]) for row in rows)) if rows else max(len(headers[i]), len(totals[i]))
            for i in range(4)
        ]

        def format_row(row):
            name = row[0].ljust(widths[0])
            nums = "  ".join(row[i].rjust(widths[i]) for i in range(1, 4))
            return f"  {name}  {nums}"

        separator = "  " + "-" * (widths[0] + sum(widths[1:]) + 6)
        lines = [format_row(headers), separator]
        lines.extend(format_row(row) for row in rows)
        lines.append(separator)
        lines.append(format_row(totals))

        start = str(Colors.GREEN) + "> " + str(Colors.WHITE) + "current selection"
        return start + "\n" + "\n".join(lines)

    @staticmethod
    def busy(text):
        return str(Colors.GREEN) + ".." + str(Colors.GREY_BRIGHT) + text + str(Colors.WHITE)

    @staticmethod
    def track(track):
        return str(Colors.BLUE) + track + str(Colors.WHITE)
