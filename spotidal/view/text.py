from enum import Enum


class Colors(Enum):
    RED = "\033[91m"
    RED_BRIGHT = "\033[38;5;132m"
    WHITE = "\033[0m"
    GREEN = "\033[38;5;70m"
    YELLOW = "\033[38;5;186m"
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
    def error(text):
        return str(Colors.RED) + " ! " + str(Colors.WHITE) + text

    @staticmethod
    def display_selection(selection):
        start = (
            str(Colors.GREEN) + "> " + str(Colors.WHITE) + "current selection [ " + str(Colors.PURPLE)
        )
        selection = ", ".join(selection)
        end = str(Colors.WHITE) + " ]"
        return start + selection + end

    @staticmethod
    def busy(text):
        return str(Colors.PURPLE) + ".." + text + str(Colors.WHITE)
